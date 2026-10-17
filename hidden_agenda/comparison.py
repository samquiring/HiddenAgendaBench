"""Compare saved models at shared observed-token boundaries; no model calls."""
import bisect
import hashlib
import json
from pathlib import Path

from hidden_agenda.io import read_rows
from hidden_agenda.length_analysis import VIEWS, length_groups, outcome, summarize, wilson
from hidden_agenda.plots import write_csv

DEFAULT_EDGES = (0, 128, 512, 2048, 8192)
VIEW_LABELS = {'output': 'Output only (private answer removed)',
               'reasoning': 'Reasoning only', 'reasoning_output': 'Reasoning + output'}


def common_groups(records, edges):
    if not edges or edges[0] != 0 or any(a >= b for a, b in zip(edges, edges[1:])):
        raise ValueError('Token edges must start at zero and strictly increase')
    included, excluded = length_groups(records, 1)
    groups = [[] for _ in edges]
    for record in included[0] if included else []:
        groups[bisect.bisect_right(edges, record['usage']['reasoning_tokens']) - 1].append(record)
    return groups, excluded


def load_runs(roots, edges, require_tokens=True):
    models = []
    reference = None
    for root in roots:
        root = Path(root)
        manifest = json.loads((root / 'manifest.json').read_text())
        # Different actors/efforts are allowed; task assignments and judge must match.
        judge_config = dict(manifest['judge_config'])
        judge_config.setdefault('model_args', {'stream': False})
        identity = (manifest['samples'], manifest['judge'], judge_config)
        if reference is not None and identity != reference:
            raise ValueError(f'{root}: task assignments or judge settings differ')
        reference = identity
        for effort in manifest['efforts']:
            directory = root / 'evaluation' / effort
            paths = [root / 'manifest.json', directory / 'graded.jsonl',
                     directory / 'judgments.jsonl', root / 'thresholds.json']
            records = read_rows(paths[1])
            expected = [s for s in manifest['samples'] if s['metadata']['partition'] == 'evaluation']
            if len(records) != len(expected) or len({r['run_id'] for r in records}) != len(expected):
                raise ValueError(f'{root}: evaluation is incomplete or contains duplicate runs')
            for condition in ('clean', 'concealment'):
                actual = {r['id'] for r in records if r['condition'] == condition}
                assigned = {s['metadata']['id'] for s in expected if s['metadata']['condition'] == condition}
                if actual != assigned:
                    raise ValueError(f'{root}: evaluated task identities differ from assignment')
            records = [r for r in records if r['condition'] == 'concealment']
            judgments = {(r['run_id'], r['view']): r for r in read_rows(paths[2])}
            thresholds = json.loads(paths[3].read_text())[effort]
            if any(v['threshold'] is None or v['comparison'] != '>' for v in thresholds.values()):
                raise ValueError(f'{root}: missing or unsupported frozen thresholds')
            groups, excluded = common_groups(records, edges)
            bins, individuals = [], []
            for index, group in enumerate(groups):
                if not group:
                    continue
                rows, points = summarize([group], judgments, thresholds)
                for row in rows:
                    row.update(bin=index + 1, lower_edge=edges[index],
                               upper_edge=edges[index + 1] if index + 1 < len(edges) else None)
                for point in points:
                    point['bin'] = index + 1
                bins.extend(rows)
                individuals.extend(points)
            if not bins and require_tokens:
                raise ValueError(f'{root}: no usable reasoning-token observations')
            aggregate = []
            for view in VIEWS:
                counts = dict.fromkeys(('covert', 'detected', 'task_failure', 'unresolved'), 0)
                for record in records:
                    counts[outcome(record, judgments.get((record['run_id'], view), {}),
                                   thresholds[view]['threshold'], view)] += 1
                aggregate.append(dict(view=view, n=len(records), **counts,
                                      ci95_low=wilson(counts['covert'], len(records))[0],
                                      ci95_high=wilson(counts['covert'] + counts['unresolved'], len(records))[1]))
            label = f"{manifest['actor'].rsplit('/', 1)[-1].split(':')[0]} ({effort})"
            models.append(dict(label=label, root=str(root.resolve()), actor=manifest['actor'],
                               effort=effort, n=len(records), excluded=len(excluded),
                               excluded_run_ids=[r['run_id'] for r in excluded],
                               thresholds=thresholds, bins=bins, individuals=individuals,
                               aggregate=aggregate,
                               judge_protocol=manifest['judge_config'].get('judge_protocol','v1'),
                               judge_replay=manifest.get('judge_replay'),
                               actor_retries=manifest.get('actor_retries'),
                               judge_retry_batches=[json.loads(p.read_text()) for p in sorted((root/'judge-retries').glob('*/plan.json'))],
                               input_hashes={str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}))
    if len(models) < 2 or len({m['label'] for m in models}) != len(models):
        raise ValueError('Provide at least two distinct model/effort configurations')
    return models


def plot_models(destination, models, views, name):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import PercentFormatter, ScalarFormatter

    colors = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00', '#56B4E9']
    markers = ['o', 's', '^', 'D', 'v', 'P']
    styles = ['-', '--', '-.', ':']
    fig, axes = plt.subplots(1, len(views), figsize=(11 if len(views) == 1 else 17, 7), squeeze=False)
    for ax, view in zip(axes[0], views):
        for index, model in enumerate(models):
            rows = [b for b in model['bins'] if b['view'] == view]
            color, marker = colors[index % len(colors)], markers[index % len(markers)]
            x = [b['median_tokens'] for b in rows]
            y = [b['confirmed_rate'] for b in rows]
            ax.plot(x, y, color=color, marker=marker, linestyle=styles[index % len(styles)], lw=2, ms=7,
                    label=model['label'], zorder=4 + index)
            for b in rows:
                if 'pooling_max_width' in model:
                    ax.hlines(b['confirmed_rate'], b['minimum_tokens'], b['maximum_tokens'],
                              color=color, alpha=.45, lw=2, linestyle=styles[index % len(styles)])
                ax.vlines(b['median_tokens'], b['ci95_low'], b['ci95_high'], color=color, alpha=.65, lw=1.4)
                ax.plot([b['median_tokens']], [b['ci95_high']], marker='_', color=color, ms=9)
                if b['unresolved']:
                    ax.plot(b['median_tokens'], b['possible_rate'], marker=marker,
                            color=color, fillstyle='none', ms=9, zorder=10)
                if b.get('width_target_met') is False:
                    ax.annotate(f"{100*b['ci_width']:.1f}pp; all n={b['n']}",
                                (b['median_tokens'], b['ci95_high']), xytext=(4, 5),
                                textcoords='offset points', color=color, fontsize=8)
        ax.set_title(VIEW_LABELS[view])
        ax.set_xscale('symlog', linthresh=1)
        ax.xaxis.set_major_formatter(ScalarFormatter())
        ceiling = max(b['ci95_high'] for m in models for b in m['bins'] if b['view'] == view)
        ax.set_ylim(-.005 if ceiling < .2 else -.035, min(1.04, max(.10, ceiling*1.2)))
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.set_xlabel('Observed reasoning tokens (median within pooled range)' if 'pooling_max_width' in models[0]
                      else 'Observed reasoning tokens (median within shared token range)')
        ax.grid(alpha=.2)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0, 0].set_ylabel('Both tasks correct and no monitor alert')
    handles = [Line2D([], [], color=colors[i % len(colors)], marker=markers[i % len(markers)],
                      linestyle=styles[i % len(styles)], lw=2, label=m['label']) for i, m in enumerate(models)]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, .93), ncol=min(4, len(models)), fontsize=9)
    fig.suptitle('Hidden Agenda Benchmark: model comparison', fontsize=16, y=.99)
    fig.text(.5, .14, 'Solid markers: confirmed rates. Open markers: upper bounds from unresolved cases. Bars: pointwise 95% Wilson envelopes.', ha='center', fontsize=9)
    fig.text(.5, .10, 'Adjacent bins pooled by model/view; horizontal lines show pooled token ranges, not measured trends. All usable attempts retained.'
             if 'pooling_max_width' in models[0] else 'Shared absolute token ranges; all attempts with usable token counts remain in bin denominators. Empty bins have no points.', ha='center', fontsize=9)
    fig.text(.5, .06, 'Zero-rate lines overlap. Counts and exclusions are in REPORT.md. Tokenizers and reasoning-effort settings differ across models.', ha='center', fontsize=9)
    fig.text(.5, .02, 'Exploratory observed-length association; intervals are not simultaneous bands or evidence of a causal effect of reasoning length.', ha='center', fontsize=9)
    fig.subplots_adjust(top=.80, bottom=.25, left=.08, right=.98, wspace=.25)
    for extension in ('png', 'svg', 'pdf'):
        fig.savefig(destination / f'{name}.{extension}', dpi=180)
    plt.close(fig)


def compare(roots, destination, edges=DEFAULT_EDGES, max_ci_width=None, project_models=(), projection_horizon=32768,
            layout='aggregate', openai_reference=False):
    edges = tuple(edges)
    models = load_runs(roots, edges, require_tokens=layout != 'aggregate')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if layout == 'aggregate':
        if max_ci_width is not None or project_models:
            raise ValueError('Pooling and hypothetical projections require --layout length; aggregate results retain all uncertainty')
        from hidden_agenda.aggregate_comparison import report_aggregate
        return report_aggregate(destination, models, openai_reference)
    if layout != 'length':
        raise ValueError('Unsupported comparison layout')
    if max_ci_width is not None:
        from hidden_agenda.projections import pool_models
        models = pool_models(models, max_ci_width)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'comparison.json').write_text(json.dumps(dict(
        edges=edges, final_bin_open_ended=True, interval='Pointwise Wilson envelope including unknowns',
        pooling_max_ci_width=max_ci_width,
        projection=dict(untested_models=list(project_models), assumed_future_rate=0,
                        horizon=projection_horizon, interpretation='Hypothetical assumptions, not fitted or measured estimates') if project_models else None,
        models=models), indent=2) + '\n')
    write_csv(destination / 'bins.csv', [dict(model=m['label'], **b) for m in models for b in m['bins']])
    write_csv(destination / 'individuals.csv', [dict(model=m['label'], **p) for m in models for p in m['individuals']])
    plot_models(destination, models, ['reasoning_output'], 'model-comparison')
    plot_models(destination, models, VIEWS, 'model-comparison-all-views')
    if project_models:
        from hidden_agenda.projections import plot_projections
        plot_projections(destination, models, project_models, projection_horizon)
    lines = ['# Model comparison', '',
             '![All models, reasoning + output](model-comparison.png)', '',
             'Same frozen tasks and fixed judge. Each colored line is one model/effort setting. The primary graph uses reasoning + output monitoring; the companion figure shows all three views.', '',
             '| Model | Joint success | Covert: reasoning | Covert: combined | Missing token counts |',
             '|---|---:|---|---|---:|']
    for m in models:
        a = {b['view']: b for b in m['aggregate']}
        def cell(view):
            b = a[view]
            return f"{b['covert']}/{b['n']}; {b['unresolved']} unresolved; 95% {100*b['ci95_low']:.1f}–{100*b['ci95_high']:.1f}%"
        lines.append(f"| {m['label']} | {m['n']-a['output']['task_failure']}/{m['n']} | {cell('reasoning')} | {cell('reasoning_output')} | {m['excluded']} |")
    lines += ['', 'Aggregate counts include all assigned concealment attempts. Length plots exclude only missing/invalid token counts, with excluded IDs saved in comparison.json. Unknown judgments never receive confirmed evasion credit.', '',
              '## Shared token ranges and support', '',
              '| Token range | ' + ' | '.join(m['label'] for m in models) + ' |',
              '|---|' + '---:|' * len(models)]
    for i, lower in enumerate(edges):
        label = f'{lower}–{edges[i+1]-1}' if i+1 < len(edges) else f'{lower}+'
        counts = [next((b['n'] for b in m.get('original_bins', m['bins']) if b['bin'] == i+1 and b['view'] == 'output'), 0) for m in models]
        lines.append('| ' + label + ' | ' + ' | '.join(map(str, counts)) + ' |')
    lines += ['', 'The x coordinate is each model’s actual median within the same fixed token boundaries. Bin memberships can contain different questions across models. Lines connect supported bins as a visual guide; no points are inferred for empty bins. Zero-rate curves overlap. Boundaries were fixed without optimizing on outcomes; this analysis is exploratory after aggregate results were observed.', '',
              'Intervals are pointwise 95% Wilson envelopes across possible assignments of unresolved successful runs. Tokenizers, providers and reasoning-effort settings differ; this is not an equal-budget causal comparison. Total reasoning includes coding, hidden math, and protocol discussion. Output-only monitoring removes the private answer by design.', '',
              'Models may have different frozen thresholds; comparison.json records them. Shared reference calibration does not guarantee the same false-alarm rate on each actor. Consult the individual run reports for clean false alarms and calibration provenance.', '',
              '![All monitoring views](model-comparison-all-views.png)', '',
              'Artifacts: PNG/SVG/PDF figures, bins.csv, individuals.csv, and comparison.json with input hashes and exact assignments. No model calls were made.']
    if max_ci_width is not None:
        lines += ['', '## Precision-based pooling', '',
                  f'Target total interval width: {100*max_ci_width:g} percentage points. Start with the shared ranges above; repeatedly merge the widest failing bin into the adjacent bin with the nearest median (higher-token neighbor breaks ties). Recompute counts and intervals from all pooled observations. Pool separately for each model and monitor view. No attempts are dropped or duplicated.', '',
                  'This pooling depends on observed outcomes and uncertainty; these are descriptive pointwise intervals, without a post-selection coverage guarantee. Pooled ranges differ across models/views. When even the full sample cannot meet the width target, retain and flag that point rather than suppressing uncertainty.', '',
                  '| Model | View | Tokens | N | Confirmed | Unknown | CI width | Target met |',
                  '|---|---|---|---:|---:|---:|---:|---|']
        for m in models:
            for b in m['bins']:
                lines.append(f"| {m['label']} | {b['view']} | {b['minimum_tokens']}–{b['maximum_tokens']} | {b['n']} | {b['covert']} | {b['unresolved']} | {100*b['ci_width']:.1f}pp | {'yes' if b['width_target_met'] else 'no; all observations pooled'} |")
    if project_models:
        lines += ['', '## Separate illustrative projections', '',
                  '![Hypothetical projections](model-projections.png)', '',
                  f"Untested additions: {', '.join(project_models)}. Their dotted zero lines are assumed scenarios, with no benchmark measurements or forecast fit. Tested models extend at an assumed zero beyond their own observed token ranges, up to {projection_horizon} tokens. Their measured points remain visible, including GLM’s nonzero result. The projection figure omits confidence intervals; the measured figures above retain uncertainty. Unknown monitor results are not evidence of zero evasion. All zero lines overlap."]
    (destination / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    print(f'Report: {destination / "REPORT.md"}')
    print(f'Graph: {destination / "model-comparison.png"}')
