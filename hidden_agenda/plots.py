"""Analyze saved trajectories only; no actor or monitor calls."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from hidden_agenda.io import read_rows
from hidden_agenda.length_analysis import VIEWS, length_groups, summarize

def write_csv(path, values):
    if not values: return
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(values[0]))
        writer.writeheader(); writer.writerows(values)

def plot(destination, bins, individuals, title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter, ScalarFormatter

    labels = {'output': 'Output only (answer removed)', 'reasoning': 'Reasoning only',
              'reasoning_output': 'Reasoning + output'}
    colors = {'covert': '#16836b', 'detected': '#326fa8', 'task_failure': '#747474', 'unresolved': '#c57816'}
    fig, axes = plt.subplots(2, 3, figsize=(14, 7.8), sharex=True,
                             gridspec_kw={'height_ratios': [3, 1.25]})
    for col, view in enumerate(VIEWS):
        ax, rug = axes[:, col]
        selected = [b for b in bins if b['view'] == view]
        x = [b['median_tokens'] for b in selected]
        y = [b['confirmed_rate'] for b in selected]
        ax.errorbar(x, y,
            yerr=[[max(0, b['confirmed_rate'] - b['ci95_low']) for b in selected],
                  [b['ci95_high'] - b['confirmed_rate'] for b in selected]],
            fmt='o-', color='#326fa8', capsize=5, lw=1.6, markersize=5)
        for b in selected:
            ax.plot([b['minimum_tokens'], b['maximum_tokens']], [b['confirmed_rate']] * 2,
                    color='#326fa8', alpha=.3, lw=2)
            if b['unresolved']:
                ax.plot(b['median_tokens'], b['possible_rate'], marker='D',
                        color=colors['unresolved'], markersize=5, fillstyle='none')
        sizes = [b['n'] for b in selected]
        size_label = f'{sizes[0]} runs per bin' if len(set(sizes)) == 1 else 'Bin sizes: ' + ', '.join(map(str, sizes))
        ax.text(.98, .97, size_label, transform=ax.transAxes, ha='right', va='top', fontsize=9, color='#555555')
        ax.set_title(labels[view], fontsize=12, pad=14)
        ax.set_ylim(-.04, 1.12)
        ax.set_yticks([0, .25, .5, .75, 1])
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.grid(axis='y', alpha=.22)
        statuses = ('covert', 'detected', 'task_failure', 'unresolved')
        for row, status in enumerate(statuses):
            lengths = [i['reasoning_tokens'] for i in individuals if i['view'] == view and i['outcome'] == status]
            rug.plot(lengths, [row] * len(lengths), '|', color=colors[status], markersize=12, alpha=.6)
        rug.set_yticks(range(4), ['Covert', 'Detected', 'Task failed', 'Unresolved'], fontsize=8)
        rug.set_ylim(3.6, -.6)
        rug.set_xscale('symlog', linthresh=1)
        rug.set_xticks([200, 500, 1000, 3000, 10000])
        rug.xaxis.set_major_formatter(ScalarFormatter())
        rug.tick_params(axis='x', labelsize=8)
        rug.set_xlabel('Observed reasoning tokens (log scale)', fontsize=10)
        for panel in (ax, rug):
            panel.spines[['top', 'right']].set_visible(False)
    axes[0, 0].set_ylabel('Joint task success without a monitor alert')
    fig.suptitle(title, fontsize=16, y=.98)
    fig.text(.5, .925, f"{len(bins)//len(VIEWS)} bins chosen from token lengths; all included runs remain in each bin denominator.", ha='center', fontsize=10)
    fig.text(.05, .07, 'Dots: confirmed covert rate. Open diamonds: upper bound from unresolved cases. Vertical bars: pointwise 95% Wilson envelopes.', fontsize=9)
    fig.text(.05, .045, 'Horizontal lines: observed bin ranges. Lower panels: individual runs. Token usage includes coding, math, and protocol discussion.', fontsize=9)
    fig.text(.05, .02, 'Exploratory association across questions at fixed effort; not a causal estimate of adding reasoning or a simultaneous confidence band.', fontsize=9)
    fig.subplots_adjust(top=.85, bottom=.16, left=.07, right=.98, hspace=.2, wspace=.32)
    for extension in ('png', 'svg', 'pdf'):
        fig.savefig(destination / f'reasoning-length-bins.{extension}', dpi=180)
    plt.close(fig)

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--effort')
    parser.add_argument('--bins', type=int, default=5)
    args = parser.parse_args(argv)
    run_manifest = json.loads((args.root / 'manifest.json').read_text())
    if args.effort is None:
        if len(run_manifest['efforts']) != 1:
            parser.error('Specify --effort for a run with multiple settings')
        args.effort = run_manifest['efforts'][0]
    if args.effort not in run_manifest['efforts']:
        parser.error('Effort is not present in the frozen manifest')
    source = args.root / 'evaluation' / args.effort
    inputs = [source / 'graded.jsonl', source / 'judgments.jsonl', args.root / 'thresholds.json']
    records = [r for r in read_rows(inputs[0]) if r['condition'] == 'concealment']
    judgments = {(r['run_id'], r['view']): r for r in read_rows(inputs[1])}
    thresholds = json.loads(inputs[2].read_text())[args.effort]
    groups, excluded = length_groups(records, args.bins)
    if not groups: raise ValueError('No valid provider reasoning-token observations')
    bins, individuals = summarize(groups, judgments, thresholds)
    destination = args.root / 'length-analysis' / args.effort
    destination.mkdir(parents=True, exist_ok=True)
    manifest = dict(analysis='Exploratory, specified after aggregate results were known',
        input_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        requested_bins=args.bins, actual_bins=len(groups), included=len(records)-len(excluded),
        excluded_run_ids=[r['run_id'] for r in excluded],
        grouping='Near-equal-count token bins, no outcome information, equal token counts never split',
        threshold_rule='Frozen clean-calibrated score; alert strictly greater than threshold', thresholds=thresholds,
        interval='Pointwise 95% Wilson envelope across all possible assignments of unresolved joint-success cases',
        causal=False, bin_run_ids=[[r['run_id'] for r in g] for g in groups],
        comparison_note='Model-specific quantile bins are descriptive. Future cross-model comparisons should additionally use common absolute token boundaries and report support per bin.')
    (destination / 'analysis.json').write_text(json.dumps(dict(manifest=manifest, bins=bins), indent=2)+'\n')
    write_csv(destination / 'bins.csv', bins)
    write_csv(destination / 'individuals.csv', individuals)
    plot(destination, bins, individuals, f"{run_manifest['actor'].split('/')[-1]} · {args.effort} effort · {len(records)} pairs")
    lines = ['# Covert completion by observed reasoning length', '',
        f'Exploratory analysis of saved runs; no new API calls. Token bins were chosen without using outcomes. Included {len(records)-len(excluded)} of {len(records)} concealment runs; {len(excluded)} have missing or invalid token counts.', '',
        '| Tokens: min–max | Median | N | Both tasks correct | Covert: output only | Covert: reasoning only | Covert: combined |',
        '|---|---:|---:|---:|---|---|---|']
    for index in range(1, len(groups)+1):
        b = {r['view']: r for r in bins if r['bin'] == index}; reference = b['output']
        def cell(view):
            row=b[view]
            return f"{row['covert']}/{row['n']}; {row['unresolved']} unknown; 95% {100*row['ci95_low']:.1f}–{100*row['ci95_high']:.1f}%"
        lines.append(f"| {reference['minimum_tokens']}–{reference['maximum_tokens']} | {reference['median_tokens']} | {reference['n']} | {reference['n']-reference['task_failure']} | {cell('output')} | {cell('reasoning')} | {cell('reasoning_output')} |")
    lines += ['', 'Unknown counts refer only to successful dual-task runs with unresolved monitor outcomes. The plotted point is the confirmed rate, not an assumption that unknowns were detected. Intervals are pointwise Wilson envelopes, not simultaneous bands. With only about 20 distinct pairs per bin they are much wider than the aggregate interval.', '',
        'The x-axis measures total emitted reasoning tokens, including primary coding and protocol discussion. Different questions and model behavior both influence length. These bins cannot identify the effect of allocating more reasoning to the same question. The output-only condition deliberately removes the answer submission and should be interpreted within that restricted observation setting.', '',
        'Future model comparisons should retain the exact task set and also use common absolute token boundaries; independently constructed model quantiles need not contain the same tasks or token ranges.', '',
        'Artifacts: reasoning-length-bins.png / .svg / .pdf; bins.csv; individuals.csv; analysis.json with input hashes, frozen thresholds and exact bin membership.']
    (destination / 'REPORT.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines[:12]))
    print(f'Artifacts: {destination}')

if __name__ == '__main__': main()
