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
