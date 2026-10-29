"""Read-only, deliberately conservative MuseScore 4 MSCX/MSCZ parser.

This is not a complete schema parser. The analysis must say 'unsupported' rather
than fabricate timing when score features are too complex.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import re
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile, BadZipFile

MAX_ARCHIVE_BYTES = 180_000_000
MAX_XML_BYTES = 125_000_000
DURATIONS = {"long": Fraction(16), "breve": Fraction(8), "whole": Fraction(4),
             "half": Fraction(2), "quarter": Fraction(1), "eighth": Fraction(1, 2),
             "16th": Fraction(1, 4), "32nd": Fraction(1, 8), "64th": Fraction(1, 16),
             "128th": Fraction(1, 32), "256th": Fraction(1, 64)}
DISALLOWED = {"Tuplet", "Tremolo", "Spanner", "endSpanner", "grace4", "grace8",
              "grace16", "grace32", "appoggiatura", "acciaccatura", "Arpeggio",
              "glissando", "TremoloSingleChord", "Tie"}
FORM_MARKERS = {"startRepeat", "endRepeat", "Jump", "Marker", "Volta", "repeatJump",
                "repeatMarker", "LayoutBreak"}


class ScoreError(ValueError):
    pass


@dataclass(frozen=True)
class Instrument:
    staff_id: str
    name: str
    chromatic: int
    diatonic: int
    percussion: bool
    staff_index: int


@dataclass(frozen=True)
class Event:
    kind: str
    duration: Fraction   # quarter-note units
    pitches: tuple[int, ...]


def _safe_xml(data: bytes) -> ET.Element:
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ScoreError('DTD and XML entities are not permitted')
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ScoreError(f'Invalid score XML: {exc}') from exc


def _text(node: ET.Element | None, key: str, default: str = '') -> str:
    return node.findtext(key, default) if node is not None else default


def _load(path: Path) -> bytes:
    if path.suffix.lower() == '.mscx':
        return path.read_bytes()
    try:
        with ZipFile(path) as z:
            members = z.infolist()
            if len(members) > 256 or sum(m.file_size for m in members) > MAX_ARCHIVE_BYTES:
                raise ScoreError('MSCZ contains too many or oversized files')
            score_name = None
            if 'META-INF/container.xml' in z.namelist():
                cont = _safe_xml(z.read('META-INF/container.xml'))
                # Main score is a top-level .mscx; Excerpts/*.mscx are embedded parts.
                # Ignore style .mss, and never auto-select an Excerpts score.
                refs = [x.get('full-path') for x in cont.iter()
                        if x.tag.endswith('rootfile') and x.get('full-path', '').lower().endswith('.mscx')
                        and '/' not in x.get('full-path', '') and '\\' not in x.get('full-path', '')]
                if len(refs) > 1:
                    raise ScoreError('Ambiguous MSCX rootfiles in archive manifest')
                score_name = refs[0] if refs else None
            if not score_name:
                matches = [n for n in z.namelist() if n.lower().endswith('.mscx') and '/' not in n and '\\' not in n]
                if len(matches) != 1:
                    raise ScoreError('Expected exactly one MSCX in MSCZ')
                score_name = matches[0]
            if score_name not in z.namelist() or z.getinfo(score_name).file_size > MAX_XML_BYTES:
                raise ScoreError('Invalid score XML member')
            # Fast fail for huge MuseScore 3 archives; do not allocate/parse
            # 100+ MB of unsupported XML just to discover its version.
            with z.open(score_name) as stream:
                header = stream.read(2048)
            match = re.search(rb'<museScore\s+version=[\"\']([^\"\']+)', header)
            if match and not match.group(1).startswith(b'4.'):
                raise ScoreError(f'Unsupported MuseScore format {match.group(1).decode("ascii", "replace")}; open and Save As in MuseScore 4 first')
            return z.read(score_name)
    except BadZipFile as exc:
        raise ScoreError('Invalid MSCZ archive') from exc


class Score:
    def __init__(self, filepath: str | Path):
        self.path = Path(filepath).expanduser().resolve(strict=True)
        if self.path.suffix.lower() not in {'.mscz', '.mscx'}:
            raise ScoreError('Only .mscx and .mscz are supported')
        if self.path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ScoreError('Score exceeds size limit')
        data = _load(self.path)
        if len(data) > MAX_XML_BYTES:
            raise ScoreError('Score XML exceeds size limit')
        self.digest = sha256(self.path.read_bytes()).hexdigest()
        self.root = _safe_xml(data)
        if self.root.tag != 'museScore' or not self.root.get('version', '').startswith('4.'):
            raise ScoreError('Only MuseScore 4.x native files are supported')
        self.version = self.root.get('version', '')
        sc = self.root.find('Score')
        if sc is None:
            raise ScoreError('Missing main Score')
        self.title = next((x.text or '' for x in sc.findall('metaTag')
                           if x.get('name') in ('workTitle', 'movementTitle') and x.text), '')
        staff_nodes = [s for s in sc.findall('Staff') if s.get('id')]
        if not staff_nodes:
            raise ScoreError('No staves found')
        self.staff_ids = [s.get('id') for s in staff_nodes]
        self.measures = {s.get('id'): s.findall('Measure') for s in staff_nodes}
        counts = {len(m) for m in self.measures.values()}
        if len(counts) != 1:
            raise ScoreError('Staves have different measure counts; cannot align')
        self.measure_count = counts.pop()
        if not self.measure_count:
            raise ScoreError('Empty score')
        self.instruments = {}
        parts = sc.findall('Part')
        self.part_count = len(parts)
        self.part_staves: dict[str, list[str]] = {}
        self.staff_to_part: dict[str, str] = {}
        self.warnings = []
        definitions = [(p, s) for p in parts for s in p.findall('Staff')]
        # MuseScore 4.4+ may omit numeric Staff/@id from Part definitions, though
        # the Score/Staff elements still have ids. For that format only, the
        # Part/Staff declarations are in score staff order. Fail closed on
        # missing/mixed counts rather than silently misassigning instruments.
        explicit = [s.get('id') for _, s in definitions]
        if all(explicit) and set(explicit) == set(self.staff_ids) and len(explicit) == len(self.staff_ids):
            sid_for = explicit
        elif not any(explicit) and len(definitions) == len(self.staff_ids):
            sid_for = self.staff_ids
            self.warnings.append('Part Staff IDs absent: mapped Part/Staff by order. Validate instrument/staff identity in MuseScore before using the plan.')
        else:
            raise ScoreError('Part/Staff mapping is ambiguous or incomplete; no safe ordinal fallback')
        part_sids_for: dict[int, list[str]] = {}
        for (part, staff_def), sid in zip(definitions, sid_for):
            part_sids_for.setdefault(id(part), []).append(sid)
        for p in parts:
            inst = p.find('Instrument')
            name = _text(p, 'trackName') or _text(inst, 'longName') or 'Unnamed part'
            instr_id = _text(inst, 'instrumentId').lower()
            chrom = int(_text(inst, 'transposeChromatic', '0') or 0)
            diat = int(_text(inst, 'transposeDiatonic', '0') or 0)
            part_sids = part_sids_for.get(id(p), [])
            if not part_sids:
                continue
            part_key = part_sids[0]
            self.part_staves[part_key] = part_sids
            for sid in part_sids:
                self.staff_to_part[sid] = part_key
            for sid, staff_def in zip(part_sids, p.findall('Staff')):
                st = staff_def.find('StaffType')
                group = st.get('group', 'pitched') if st is not None else 'pitched'
                self.instruments[sid] = Instrument(sid, name, chrom, diat,
                  instr_id.startswith(('drum', 'percussion')) or group in ('percussion', 'tab'),
                  self.staff_ids.index(sid))
        self.lengths = self._lengths()
        if self.part_count != len(self.instruments):
            self.warnings.append('Some instruments have multiple staves; verify live staff ordering')
        if any(not self.instruments.get(s) for s in self.staff_ids):
            self.warnings.append('Unmapped staff definitions will be skipped')

    def _lengths(self) -> list[Fraction]:
        # TimeSig can be stored only on staff 1; measures may have len override (pickup).
        m0 = self.measures[self.staff_ids[0]]
        n, d = 4, 4
        lengths = []
        for m in m0:
            ts = next(m.iter('TimeSig'), None)
            if ts is not None:
                n = int(_text(ts, 'sigN', str(n)))
                d = int(_text(ts, 'sigD', str(d)))
            if n <= 0 or d <= 0:
                raise ScoreError('Invalid time signature')
            try:
                val = Fraction(4) * Fraction(m.get('len')) if m.get('len') else Fraction(4*n, d)
            except (ValueError, ZeroDivisionError) as exc:
                raise ScoreError('Invalid measure duration') from exc
            if val <= 0:
                raise ScoreError('Nonpositive measure duration')
            lengths.append(val)
        return lengths

    def has_notes(self, sid: str, index: int) -> bool:
        return any(x.tag == 'Chord' for x in self.measures[sid][index].iter())

    def has_part_notes(self, part_key: str, index: int) -> bool:
        """Sounding/rest classification requires all staves belonging to one Part."""
        return any(self.has_notes(sid, index) for sid in self.part_staves[part_key])

    def source_label(self, sid: str) -> str:
        inst = self.instruments[sid]
        group = self.part_staves.get(self.staff_to_part[sid], [sid])
        if len(group) == 1:
            return inst.name
        return f'{inst.name} (staff {group.index(sid)+1}/{len(group)})'

    def form_risk(self, start: int, end: int) -> bool:
        # Conservatively flag form markers in any staff around a transition.
        for i in range(max(0, start - 1), min(self.measure_count, end + 2)):
            for sid in self.staff_ids:
                m = self.measures[sid][i]
                if any(e.tag in FORM_MARKERS or e.tag.lower().endswith('repeat') for e in m.iter()):
                    return True
        return False

    def timing_risks(self, start: int, end: int) -> list[str]:
        """Describe notation changes affecting a cue window / entry.

        These are inspection flags, not proof that automatic copying is unsafe.
        Only one warning per change type is emitted, regardless of staff count.
        """
        changes = {'KeySig': 'key_signature_change_nearby',
                   'TimeSig': 'time_signature_change_nearby',
                   'Tempo': 'tempo_change_nearby'}
        found: set[str] = set()
        for i in range(max(0, start), min(self.measure_count, end + 1)):
            for sid in self.staff_ids:
                for e in self.measures[sid][i].iter():
                    if e.tag in changes:
                        found.add(changes[e.tag])
        return [v for v in changes.values() if v in found]

    def timing_risk(self, start: int, end: int) -> bool:
        """Backwards-compatible aggregate boolean."""
        return bool(self.timing_risks(start, end))

    def simple_events(self, sid: str, index: int) -> tuple[Event, ...] | None:
        """Full-measure first-voice timeline, or None if uncertain. No guessing."""
        measure = self.measures[sid][index]
        voices = measure.findall('voice')
        if len(voices) != 1:
            return None
        voice = voices[0]
        if any(e.tag in DISALLOWED or e.tag == 'tick' for e in voice.iter()):
            return None
        events = []
        for e in voice:
            if e.tag not in {'Chord', 'Rest'}:
                continue   # annotations do not advance time
            kind = e.tag
            dt = _text(e, 'durationType')
            if dt == 'measure':
                duration = self.lengths[index]
            elif dt in DURATIONS:
                duration = DURATIONS[dt]
                dots = int(_text(e, 'dots', '0') or 0)
                if dots < 0 or dots > 3:
                    return None
                duration *= 2 - Fraction(1, 2**dots)
            else:
                return None
            notes = e.findall('Note') if kind == 'Chord' else []
            if kind == 'Chord' and (not notes or len(notes) > 1):
                return None  # monophonic melody only for safe preview
            pitches = []
            for note in notes:
                try:
                    pitch = int(_text(note, 'pitch'))
                    if pitch < 0 or pitch > 127 or note.find('tpc') is None:
                        return None
                    pitches.append(pitch)
                except ValueError:
                    return None
            events.append(Event(kind, duration, tuple(pitches)))
        if not events or sum((e.duration for e in events), Fraction(0)) != self.lengths[index]:
            return None
        return tuple(events)
