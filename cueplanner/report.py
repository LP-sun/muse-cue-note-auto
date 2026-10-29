"""Human-readable review output. Generated without changing original score."""
from __future__ import annotations


def markdown(plan: dict) -> str:
    rows = [
        '# Orchestral Cue review plan',
        '',
        f'**Source:** `{plan["source"]}`',
        f'**SHA-256:** `{plan["source_sha256"]}`',
        f'**Score measures:** {plan["measure_count"]}',
        f'**Candidates:** {len(plan["candidates"])}',
        '',
        '> Analysis only; no notes have been added. Check all choices by ear and in MuseScore.',
        '',
    ]
    for c in plan['candidates']:
        rows.extend([
            f'## {c["target"]} — entry measure {c["entry_measure"]}',
            '',
            f'- **Rest:** bars {c["rest_from"]}–{c["rest_to"]} ({c["rest_bars"]} bars)',
            f'- **Cue window:** bars {c["cue_from"]}–{c["cue_to"]}',
            f'- **Candidate ID:** `{c["id"]}`',
            '',
            '| Rank | Source | Heuristic score | Notes/bar | Risks |',
            '|---:|---|---:|---:|---|',
        ])
        for i, s in enumerate(c['sources'], 1):
            risks = ', '.join(s['risk_flags']) or 'none detected'
            rows.append(f'| {i} | {s["source"]} | {s["score"]} | '
                        f'{s["features"]["notes_per_bar"]} | {risks} |')
        rows += ['', '- [ ] Audibly identifiable cue source',
                 '- [ ] Target instrument transposition/clef checked',
                 '- [ ] Repeats and time signature checked',
                 '- [ ] Bar numbers verified in actual part', '']
    rows += ['## Limitations', '']
    rows.extend(f'- {warning}' for warning in plan['warnings'])
    rows += ['', 'Scoring is a heuristic, not a perceptual or engraving guarantee.', '']
    return '\n'.join(rows)
