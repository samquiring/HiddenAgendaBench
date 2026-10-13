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
    report = commands.add_parser('report', help='Regenerate the aggregate report without model calls')
    report.add_argument('--root', type=Path, required=True)
    analyze = commands.add_parser('analyze', help='Generate length plots and CSVs from saved results')
    analyze.add_argument('--root', type=Path, required=True)
    analyze.add_argument('--effort')
    analyze.add_argument('--bins', type=int, default=5)
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
            run(args.root, manifest)
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
