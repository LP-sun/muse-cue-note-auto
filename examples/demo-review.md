# Orchestral Cue review plan

**Source:** `examples/demo-orchestra.mscz`
**SHA-256:** `fd77d3d54395f3cc747c51dde6bb8cd71bfe13a1068f4bcad1db5d469a79c944`
**Score measures:** 12
**Candidates:** 1

> Analysis only; no notes have been added. Check all choices by ear and in MuseScore.

## Clarinet in B♭ — entry measure 12

- **Rest:** bars 1–11 (11 bars)
- **Cue window:** bars 10–11
- **Candidate ID:** `2@12`

| Rank | Source | Heuristic score | Notes/bar | Risks |
|---:|---|---:|---:|---|
| 1 | Flute | 47.0 | 4.0 | target_instrument_transposition |
| 2 | Oboe | 45.5 | 4.0 | target_instrument_transposition |

- [ ] Audibly identifiable cue source
- [ ] Target instrument transposition/clef checked
- [ ] Repeats and time signature checked
- [ ] Bar numbers verified in actual part

## Limitations

- Only straightforward monophonic first-voice source passages are eligible.
- Cue rank estimates rhythmic/melodic distinctiveness, not actual audibility.
- MCP Score Bridge supplies metadata and navigation, not full-measure note extraction.
- No changes have been made to the score; every candidate requires human review.

Scoring is a heuristic, not a perceptual or engraving guarantee.
