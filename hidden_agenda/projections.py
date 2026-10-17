"""Exploratory precision-based pooling and explicitly hypothetical projections."""
from collections import Counter
from copy import deepcopy
from statistics import median

from hidden_agenda.length_analysis import VIEWS, wilson


def pooled_row(points, view, index):
    counts = Counter(p['outcome'] for p in points)
    n = len(points)
    k, unknown = counts['covert'], counts['unresolved']
    tokens = [p['reasoning_tokens'] for p in points]
    low, high = wilson(k, n)[0], wilson(k + unknown, n)[1]
    return dict(bin=index, view=view, n=n, minimum_tokens=min(tokens), maximum_tokens=max(tokens),
                median_tokens=median(tokens), covert=k, unresolved=unknown,
                detected=counts['detected'], task_failure=counts['task_failure'],
                confirmed_rate=k/n, possible_rate=(k+unknown)/n,
                ci95_low=low, ci95_high=high, ci_width=high-low,
                run_ids=[p['run_id'] for p in points])


def pool_models(models, max_width):
    if not 0 < max_width < 1:
        raise ValueError('CI width must be between zero and one')
    result = deepcopy(models)
    for model in result:
        model['original_bins'] = model['bins']
        model['bins'] = []
        for view in VIEWS:
            points = [p for p in model['individuals'] if p['view'] == view]
            ids = sorted({p['bin'] for p in points})
            groups = [[p for p in points if p['bin'] == index] for index in ids]
            while len(groups) > 1:
                rows = [pooled_row(g, view, i+1) for i, g in enumerate(groups)]
                bad = [i for i, r in enumerate(rows) if r['ci_width'] > max_width]
                if not bad:
                    break
                i = max(bad, key=lambda j: (rows[j]['ci_width'], -j))
                neighbors = [j for j in (i-1, i+1) if 0 <= j < len(groups)]
                j = min(neighbors, key=lambda j: (abs(rows[j]['median_tokens']-rows[i]['median_tokens']), -j))
                left, right = sorted((i, j))
                groups[left] += groups[right]
                del groups[right]
            for i, group in enumerate(groups, 1):
                row = pooled_row(group, view, i)
                row['width_target_met'] = row['ci_width'] <= max_width
                model['bins'].append(row)
                for point in group:
                    point['pooled_bin'] = i
        model['pooling_max_width'] = max_width
    return result


def plot_projections(destination, models, names, horizon):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import PercentFormatter, ScalarFormatter

    observed_max = max(p['reasoning_tokens'] for m in models for p in m['individuals'])
    if horizon <= observed_max:
        raise ValueError(f'Projection horizon must exceed observed maximum ({observed_max} tokens)')
    colors = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00', '#56B4E9']
    all_labels = [m['label'] for m in models] + list(names)
    fig, axes = plt.subplots(1, 2, figsize=(15, 7), sharey=True)
    for ax, view, title in zip(axes, ('reasoning', 'reasoning_output'), ('Reasoning only', 'Reasoning + output')):
        for i, label in enumerate(all_labels):
            color = colors[i % len(colors)]
            untested = i >= len(models)
            # All six scenarios assume zero future evasion; no synthetic samples or CIs.
            start = 32 if untested else max(p['reasoning_tokens'] for p in models[i]['individuals'])
            ax.plot([start, horizon], [0, 0], color=color, linestyle=':' if untested else '--',
                    linewidth=2.2, zorder=2+i)
            # Place colored hollow markers along coincident scenario lines for visibility.
            marker_x = start * (horizon/start)**((i+1)/(len(all_labels)+1))
            ax.plot(marker_x, 0, marker='D' if untested else 's', fillstyle='none',
                    color=color, ms=7, zorder=20+i)
            if not untested:
                rows = [b for b in models[i]['bins'] if b['view'] == view]
                ax.plot([b['median_tokens'] for b in rows], [b['confirmed_rate'] for b in rows],
                        linestyle='-', marker='o', color=color, lw=1.5, ms=5, zorder=10+i)
        ax.set_xscale('log')
        ax.set_xlim(20, horizon*1.05)
        ax.xaxis.set_major_formatter(ScalarFormatter())
        ax.set_ylim(-.003, .04)
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.set_title(title)
        ax.set_xlabel('Reasoning tokens (log scale)')
        ax.grid(alpha=.2)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].set_ylabel('Joint task success without a monitor alert')
    handles = [Line2D([], [], color=colors[i % len(colors)], linestyle=':' if i >= len(models) else '--',
                      label=f'{label} — untested scenario' if i >= len(models) else f'{label} — zero extrapolation')
               for i, label in enumerate(all_labels)]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, .92), ncol=3, fontsize=9)
    fig.suptitle('Illustrative zero-evasion projections — Astra and Sol have NOT been evaluated', fontsize=15, y=.99)
    fig.text(.5, .15, 'Solid lines / circles: measured confirmed rates. Dashed lines: assumed zero beyond each tested model’s observed token range.', ha='center', fontsize=9)
    fig.text(.5, .10, 'Dotted Astra / Sol lines: hypothetical zero-evasion scenarios across the entire range; no measured data support these additions.', ha='center', fontsize=9)
    fig.text(.5, .05, 'All zero scenario lines coincide. Hollow markers distinguish colors. These are assumptions, not fitted forecasts; see measured graph for uncertainty.', ha='center', fontsize=9)
    fig.subplots_adjust(top=.75, bottom=.25, left=.07, right=.98, wspace=.15)
    for extension in ('png', 'svg', 'pdf'):
        fig.savefig(destination / f'model-projections.{extension}', dpi=180)
    plt.close(fig)
