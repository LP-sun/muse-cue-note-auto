# DSH MuseScore Cue Planner Bundle v0.3.0

This is the standalone DSH bundle (including the Python engine under `cueplanner/`).

1. Set an existing scores root in `cordis.patch.yml` (edit `config.root`).
2. Install to the **actual active** DSH profile with `dsh plugin --profile <profile> add link:<absolute-path-to-this-folder>`.
3. Run `node --test tests/*.test.mjs` and the `musescore_cue_analyze` tool first.
4. MuseScore real-time checks additionally require upstream `mcp-score` and MuseScore Studio 4.4.2+ with MCP Score Bridge open.

Six tools: `musescore_cue_analyze`, `musescore_cue_batch`, `musescore_cue_candidate`, `musescore_cue_bridge_check`, `musescore_cue_live_verify`, `musescore_cue_focus`.

**Read-only analyzer.** No score notes are inserted or changed; focus only changes GUI selection. If a native DSH installation is newer or has API differences, inspect upstream DSH documentation and adapt locally rather than assuming real host verification.

For full instructions see the project root README.
