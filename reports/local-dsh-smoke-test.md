# Local DSH smoke test

- Python 3.13.0; Node v24.12.0; MuseScore 4 installed under C:/Program Files/MuseScore 4.
- DSH CLI: unavailable on PATH; desktop profile found at C:/Users/Lenovo/.dsh/profiles/desktop.
- Python tests: 16/16 passed.
- Node tests: 2/4 passed; 2 symlink tests blocked by Windows EPERM (Developer Mode/SeCreateSymbolicLinkPrivilege unavailable).
- Runtime fixed Windows python3 fallback to python.
- Six tool definitions present in dsh-plugin/index.js; actual DSH registration not verified because CLI unavailable.
- mcp-score/uv unavailable; MuseScore Bridge real connection, live_verify and focus not executed.
- Input scores were not modified.
- Commit: a46c663 (amended locally after cleanup).
- Push: https://github.com/LP-sun/muse-cue-note-auto/tree/feat/musescore-cue-dsh

- Located DSH desktop Profile at C:/Users/Lenovo/.dsh/profiles/desktop; installed bundle copy at its node_modules/dsh-musescore-cue-planner and added profile patch/dependency. DSH executable itself is not exposed as a CLI command, so reload/tool-list evidence remains pending desktop restart.

- Added isolated uv 0.13.6, Python 3.14.10, and upstream mcp-score-server 0.2.0 from tskovlund/mcp-score source. install-plugin succeeded at C:/Users/Lenovo/Documents/MuseScore4/Plugins/mcp-score-bridge. MuseScore demo-orchestra.mscx opened read-only. Bridge GUI still needs enabling/running.

- REAL BRIDGE VERIFIED: port 8765 listening; bridge-check returned MuseScore/Cue Test Suite, 3 parts, 12 measures. live-verify metadata checks passed (identity_proven false by design). focus candidate 2@12 selected Clarinet staff 1 at measure 10 with no note changes.

- Requested batch ZIP inspected: it contains 6 prior cue-plan/review pairs plus summary, not original scores; no source scores were added to Git. Fresh batch against Documents/MuseScore4/Scores analyzed 2 local MSCZ files, produced 2 plans, 0 candidates each, without modifying inputs. Python regression remains 16/16 passed.
