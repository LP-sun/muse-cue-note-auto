"""CLI for offline analysis and MCP Score Bridge verification/navigation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from .analysis import Settings, analyze
from .mcp_bridge import ScoreMcpClient, BridgeError, verify_live
from .score import ScoreError
from .report import markdown


def _json(x):
    print(json.dumps(x, ensure_ascii=False, indent=2))


def _setting_args(p):
    p.add_argument('--min-rest', type=int, default=8)
    p.add_argument('--cue-bars', type=int, default=2)
    p.add_argument('--top-sources', type=int, default=4)
    p.add_argument('--same-transposition-only', action='store_true')


def _bridge_args(p):
    p.add_argument('--mcp-exe', default='mcp-score', help='Executable path of external mcp-score server')
    p.add_argument('--mcp-arg', action='append', help='Override server args, repeatable; default: serve')
    p.add_argument('--host', default='localhost', choices=('localhost','127.0.0.1','::1'))
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--timeout', type=float, default=20.0)


def _settings(a):
    return Settings(a.min_rest, a.cue_bars, a.top_sources, not a.same_transposition_only)


def _connect(a):
    return ScoreMcpClient(a.mcp_exe, tuple(a.mcp_arg if a.mcp_arg is not None else ['serve']), a.timeout)


def _path_for(source):
    return Path(source).expanduser().resolve(strict=True)


def main(argv=None):
    p = argparse.ArgumentParser(prog='cue-planner', description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    pa = sub.add_parser('analyze', help='Generate a read-only JSON cue plan from MSCX/MSCZ')
    pa.add_argument('score')
    _setting_args(pa)
    pa.add_argument('--output', help='Path for new JSON file; defaults to stdout')
    pa.add_argument('--markdown', help='Optional new human-review Markdown report path')
    pb = sub.add_parser('batch', help='Analyze all MSCX/MSCZ in directory, plans only')
    pb.add_argument('directory')
    _setting_args(pb)
    pb.add_argument('--out-dir', help='Write plans here; do not overwrite')
    pb.add_argument('--limit', type=int, default=100)
    pc = sub.add_parser('bridge-check', help='Connect via external mcp-score and show active MuseScore metadata')
    _bridge_args(pc)
    pv = sub.add_parser('live-verify', help='Compare on-disk score metadata with live MuseScore metadata')
    pv.add_argument('score')
    _bridge_args(pv)
    pf = sub.add_parser('focus', help='Select a cue destination in MuseScore (no note modifications)')
    pf.add_argument('score')
    pf.add_argument('--candidate', required=True, help='Candidate id such as 2@12')
    pf.add_argument('--at', choices=('cue','entry'), default='cue')
    _setting_args(pf)
    _bridge_args(pf)
    args = p.parse_args(argv)
    try:
        if args.cmd == 'analyze':
            result = analyze(args.score, _settings(args))
            if args.markdown:
                mdout = Path(args.markdown).expanduser().resolve()
                if mdout.exists():
                    raise ValueError(f'Refusing to overwrite existing file {mdout}')
                mdout.parent.mkdir(parents=True, exist_ok=True)
                mdout.write_text(markdown(result), encoding='utf-8')
            if args.output:
                out = Path(args.output).expanduser().resolve()
                if out.exists():
                    raise ValueError(f'Refusing to overwrite existing file {out}')
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                _json({'plan':str(out), 'candidate_count':len(result['candidates']), 'stats':result['stats']})
            else:
                _json(result)
        elif args.cmd == 'batch':
            if not 1 <= args.limit <= 1000:
                raise ValueError('limit must be 1..1000')
            path = _path_for(args.directory)
            if not path.is_dir():
                raise ValueError('Not a directory')
            # Never follow links to score files outside the explicitly selected batch dir.
            scores = sorted(x for x in path.iterdir() if x.is_file() and x.suffix.lower() in ('.mscx', '.mscz')
                            and x.resolve().is_relative_to(path))[:args.limit]
            results = []
            destination = Path(args.out_dir).expanduser().resolve() if args.out_dir else None
            if destination:
                destination.mkdir(parents=True, exist_ok=True)
            for file in scores:
                try:
                    plan = analyze(file, _settings(args))
                    item = {'score':str(file), 'candidate_count':len(plan['candidates'])}
                    if destination:
                        out = destination / (file.name + '.cue-plan.json')
                        if out.exists():
                            raise ValueError(f'Output already exists: {out}')
                        out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
                        item['plan_path'] = str(out)
                    else:
                        item['candidates'] = plan['candidates']
                    results.append(item)
                except (ScoreError, OSError, ValueError) as exc:
                    results.append({'score':str(file), 'error':str(exc)})
            _json({'analyzed':len(results), 'results':results})
        elif args.cmd == 'bridge-check':
            with _connect(args) as mcp:
                _json(mcp.connect(args.host, args.port))
        elif args.cmd in ('live-verify','focus'):
            plan = analyze(args.score, _settings(args) if args.cmd == 'focus' else Settings())
            with _connect(args) as mcp:
                live = mcp.connect(args.host, args.port)
                verification = verify_live(plan, live['live_score'])
                if args.cmd == 'live-verify':
                    _json(verification)
                else:
                    if not verification['metadata_consistent']:
                        raise BridgeError('Live score metadata inconsistent; refusing to focus wrong score')
                    choice = next((c for c in plan['candidates'] if c['id'] == args.candidate), None)
                    if choice is None:
                        raise ValueError(f'Unknown candidate id: {args.candidate}')
                    measure = choice['cue_from'] if args.at == 'cue' else choice['entry_measure']
                    selected = mcp.select_measure(measure, choice['target_staff_index'])
                    _json({'selection':selected, 'target':choice['target'], 'measure':measure,
                           'staff_zero_based':choice['target_staff_index'], 'verification':verification,
                           'warning':'Selection only. No note changes. Verify the open score manually.'})
    except (ScoreError, BridgeError, OSError, ValueError, KeyError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
