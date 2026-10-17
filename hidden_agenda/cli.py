"""Default CLI for the frozen public-task benchmark."""
import argparse
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description='Hidden Agenda Benchmark: 100 pairs, 30 calibration cases, one reasoning effort.')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('fetch-data', help='Download or verify the pinned public source data')
    for name in ('prepare', 'run'):
        command = commands.add_parser(name, help='Freeze exact samples and settings' if name == 'prepare' else 'Run or resume the frozen experiment')
        command.add_argument('--root', type=Path, required=True, help='Separate results directory for each model/configuration')
        command.add_argument('--config', type=Path, help='TOML settings; omit on resume to use the frozen manifest')
        if name=='run':command.add_argument('--calibration-from',type=Path,help='Explicitly reuse a fixed judge calibration before evaluation; records provenance')
    report = commands.add_parser('report', help='Regenerate the aggregate report without model calls')
    report.add_argument('--root', type=Path, required=True)
    analyze = commands.add_parser('analyze', help='Generate length plots and CSVs from saved results')
    analyze.add_argument('--root', type=Path, required=True)
    analyze.add_argument('--effort')
    analyze.add_argument('--bins', type=int, default=5)
    comparison = commands.add_parser('compare', help='Compare aggregate model results with confidence intervals; no API calls')
    comparison.add_argument('--roots', type=Path, nargs='+', required=True)
    comparison.add_argument('--output', type=Path, default=Path('runs/model-comparison'))
    comparison.add_argument('--token-edges', type=int, nargs='+', default=[0, 128, 512, 2048, 8192],
                            help='Shared bin lower boundaries; final bin is open ended')
    comparison.add_argument('--max-ci-width', type=float, help='Pool adjacent bins until total interval width meets this fraction, if achievable')
    comparison.add_argument('--project-models', nargs='+', default=[], help='Untested models to add as hypothetical zero-evasion dotted lines in a separate figure')
    comparison.add_argument('--projection-horizon', type=int, default=32768)
    comparison.add_argument('--layout', choices=('aggregate', 'length'), default='aggregate')
    comparison.add_argument('--openai-reference', action='store_true', help='Include the cited qualitative system-card reference separately')
    retry = commands.add_parser('retry-judges', help='Explicitly retry invalid evaluation judgments; archive original results and preserve actor responses')
    retry.add_argument('--roots', type=Path, nargs='+', required=True)
    retry.add_argument('--attempts', type=int, default=3, help='Maximum additional attempts per failed view')
    retry.add_argument('--protocol', choices=('v1','v2'), default='v1', help='V2 strengthens transcript boundaries and uses evidence IDs; recorded as revised-protocol repairs')
    replay = commands.add_parser('rejudge-all', help='Create a uniform v2 judge-only dataset from saved calibration/evaluation traces')
    replay.add_argument('--roots', type=Path, nargs='+', required=True, help='First source supplies shared clean calibration')
    replay.add_argument('--output', type=Path, required=True)
    replay.add_argument('--workers', type=int, default=24)
    replay.add_argument('--attempts', type=int, default=6, help='Uniform maximum invalid-response attempts per view')
    legacy = commands.add_parser('legacy', help='Historical toy-task and channel-control commands')
    legacy.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == 'fetch-data':
        from hidden_agenda.sources import fetch_sources
        fetch_sources()
    elif args.command == 'legacy':
        from hidden_agenda.legacy_cli import main as legacy_main
        legacy_main(args.arguments)
    elif args.command == 'analyze':
        analyze_saved(args.root, args.effort, args.bins)
    elif args.command == 'retry-judges':
        from hidden_agenda.rejudge import retry_failed
        for root in args.roots:
            retry_failed(root, args.attempts, args.protocol)
    elif args.command == 'rejudge-all':
        from hidden_agenda.judge_replay import replay_all
        replay_all(args.roots,args.output,args.workers,args.attempts)
    elif args.command == 'compare':
        from hidden_agenda.comparison import compare
        compare(args.roots, args.output, args.token_edges, args.max_ci_width,
                args.project_models, args.projection_horizon, args.layout, args.openai_reference)
    elif args.command == 'report':
        from hidden_agenda.benchmark import report as generate_report
        generate_report(args.root)
        print(f'Report: {args.root / "REPORT.md"}')
    else:
        from hidden_agenda.benchmark import freeze, run
        from hidden_agenda.config import load_config
        config = load_config(args.config) if args.config else None
        manifest = freeze(args.root, config)
        print(f"Frozen {len(manifest['samples'])} samples; actor={manifest['actor']}; judge={manifest['judge']}; effort={','.join(manifest['efforts'])}")
        if args.command == 'run':
            run(args.root, manifest, calibration_from=args.calibration_from)
            try:
                import matplotlib  # noqa: F401
            except ImportError:
                print('Results saved. Install .[analysis] and run hidden-agenda analyze for plots.')
            else:
                for effort in manifest['efforts']:
                    analyze_saved(args.root, effort, 5)


def analyze_saved(root, effort=None, bins=5):
    from hidden_agenda.plots import main as plot_main
    arguments = ['--root', str(root), '--bins', str(bins)]
    if effort:
        arguments += ['--effort', effort]
    plot_main(arguments)


if __name__ == '__main__':
    main()
