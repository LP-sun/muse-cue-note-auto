"""Explainable orchestral cue candidate detection and ranking (read-only)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any
from .score import Score, Event


@dataclass(frozen=True)
class Settings:
    min_rest: int = 8
    cue_bars: int = 2
    top_sources: int = 4
    allow_cross_transposition: bool = True

    def validate(self):
        if not 2 <= self.min_rest <= 128:
            raise ValueError('min_rest must be between 2 and 128')
        if not 1 <= self.cue_bars <= 4:
            raise ValueError('cue_bars must be between 1 and 4')
        if not 1 <= self.top_sources <= 10:
            raise ValueError('top_sources must be between 1 and 10')


def _rank(events: list[Event], cue_bars: int, cross: bool) -> tuple[float, dict[str, Any]]:
    notes = [e for e in events if e.kind == 'Chord']
    pitches = [e.pitches[0] for e in notes]
    dur = [e.duration for e in notes]
    # A recognizable rhythmic / melodic phrase is more useful than a sustained pad.
    interval = [b - a for a, b in zip(pitches, pitches[1:])]
    contour = [1 if d > 0 else -1 for d in interval if d != 0]
    direction_changes = sum(a != b for a, b in zip(contour, contour[1:]))
    duration_kinds = len(set(dur))
    onsets = len(notes)
    density = onsets / cue_bars
    # Ranking heuristic, not a measure of real-world audibility.
    detail = {
        'note_onsets': onsets,
        'notes_per_bar': round(density, 2),
        'rhythmic_values': duration_kinds,
        'contour_changes': direction_changes,
        'range_semitones': max(pitches) - min(pitches),
        'transposition_difference': cross,
    }
    points = 20
    points += min(onsets, 10) * 2.5
    points += min(duration_kinds, 4) * 4
    points += min(direction_changes, 3) * 3
    points += min(max(pitches) - min(pitches), 12) * .5
    points -= abs(density - 3.0) * 3
    if onsets <= cue_bars:
        points -= 16
    if density > 6:
        points -= (density - 6) * 4
    if cross:
        points -= 3  # copy must be transposed for target part in a future writer
    return round(points, 1), detail


def analyze(path: str | Path, settings: Settings = Settings()) -> dict:
    settings.validate()
    sc = Score(path)
    candidates = []
    skipped = Counter()
    # Iterate musical parts, not individual staves: piano LH is not a separate
    # instrument merely because its treble/RH staff is playing.
    for part_key, part_sids in sc.part_staves.items():
        target_sid = part_sids[0]
        target = sc.instruments.get(target_sid)
        if target is None or target.percussion:
            skipped['unmapped_or_percussion_targets'] += 1
            continue
        target_measures = sc.measures[target_sid]
        index = 0
        while index < sc.measure_count:
            if sc.has_part_notes(part_key, index):
                index += 1
                continue
            rest_start = index
            while index < sc.measure_count and not sc.has_part_notes(part_key, index):
                index += 1
            entry = index  # zero-based first sounded measure
            if entry >= sc.measure_count:
                if rest_start == 0:
                    skipped['parts_entirely_silent'] += 1
                elif entry - rest_start >= settings.min_rest:
                    skipped['end_silence_no_reentry'] += 1
                continue
            if entry - rest_start < settings.min_rest:
                continue
            skipped['long_rest_reentries_found'] += 1
            cue_start = max(rest_start, entry - settings.cue_bars)
            window = list(range(cue_start, entry))
            # Safety: do not use rests in a structurally complex/multi-voice target.
            if any(len(target_measures[i].findall('voice')) != 1 for i in window):
                skipped['complex_target_voices'] += 1
                continue
            options = []
            for source_sid in sc.staff_ids:
                if sc.staff_to_part.get(source_sid) == part_key:
                    continue  # do not cue a piano using its own other staff
                source = sc.instruments.get(source_sid)
                if source is None or source.percussion:
                    continue
                cross = (source.chromatic, source.diatonic) != (target.chromatic, target.diatonic)
                if cross and not settings.allow_cross_transposition:
                    continue
                fragments = [sc.simple_events(source_sid, i) for i in window]
                if any(x is None for x in fragments):
                    skipped['source_complex_timing_or_chords'] += 1
                    continue
                # Each cue bar must contain at least one melodic note.
                if any(not any(e.kind == 'Chord' for e in part) for part in fragments):
                    continue
                phrase = [e for part in fragments for e in part]
                if sum(e.kind == 'Chord' for e in phrase) < 2:
                    continue
                pts, features = _rank(phrase, len(window), cross)
                risks = []
                if cross:
                    risks.append('target_instrument_transposition')
                if sc.form_risk(cue_start, entry):
                    risks.append('repeat_or_navigation_marking_nearby')
                risks.extend(sc.timing_risks(cue_start, entry))
                options.append({
                    'id': f'{target_sid}@{entry+1}<-{source_sid}@{cue_start+1}',
                    'source_staff': source_sid,
                    'source_staff_index': source.staff_index,
                    'source': sc.source_label(source_sid),
                    'score': pts,
                    'features': features,
                    'risk_flags': risks,
                    'preview_sounding_midi': [e.pitches[0] for e in phrase if e.pitches][:24],
                })
            options.sort(key=lambda x: (-x['score'], x['source_staff_index']))
            # Avoid two nearly equivalent hands of the same piano taking
            # multiple slots in the recommended instrument alternatives.
            best_per_part = []
            seen_parts = set()
            for option in options:
                source_part = sc.staff_to_part[option['source_staff']]
                if source_part not in seen_parts:
                    best_per_part.append(option)
                    seen_parts.add(source_part)
            options = best_per_part
            if not options:
                skipped['no_safe_source_melody'] += 1
                continue
            candidates.append({
                'id': f'{target_sid}@{entry+1}',
                'target': target.name,
                'target_staff': target_sid,
                'target_staff_index': target.staff_index,
                'rest_from': rest_start+1,
                'rest_to': entry,
                'rest_bars': entry-rest_start,
                'cue_from': cue_start+1,
                'cue_to': entry,
                'entry_measure': entry+1,
                'sources': options[:settings.top_sources],
                'recommended_source_id': options[0]['id'],
                'review_required': True,
            })
    candidates.sort(key=lambda c: (c['entry_measure'], c['target_staff_index']))
    return {
        'schema_version': '1.0',
        'engine': 'mcp-score-cue-planner/0.3.0',
        'source': str(sc.path),
        'source_sha256': sc.digest,
        'musescore_format_version': sc.version,
        'title': sc.title,
        'measure_count': sc.measure_count,
        'part_count': sc.part_count,
        'staff_count': len(sc.staff_ids),
        'settings': {k: getattr(settings, k) for k in Settings.__dataclass_fields__},
        'candidates': candidates,
        'stats': {'entries_with_cues': len(candidates), 'skipped': dict(skipped)},
        'warnings': sc.warnings + [
          'Only straightforward monophonic first-voice source passages are eligible; target silence is evaluated across an entire Part.',
          'Cue rank estimates rhythmic/melodic distinctiveness, not actual audibility.',
          'MCP Score Bridge supplies metadata and navigation, not full-measure note extraction.',
          'No changes have been made to the score; every candidate requires human review.'
        ]
    }
