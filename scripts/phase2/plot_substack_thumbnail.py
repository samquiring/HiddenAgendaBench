"""Original five-model CoT aggregate results as an exact 1200 x 630 thumbnail."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

LABELS = {
    'DeepSeek-V4.1-Flash (low)': 'DeepSeek V4.1 Flash',
    'GLM-5.3 (high)': 'GLM-5.3',
    'DeepSeek-V4-Pro (high)': 'DeepSeek V4 Pro',
    'Kimi-K3 (high)': 'Kimi K3',
    'Qwen3.8-2.4T-A95B (xhigh)': 'Qwen3.8 2.4T',
}
COLORS = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00']


def build(source, output):
    with source.open(newline='') as stream:
        rows = [r for r in csv.DictReader(stream) if r['view'] == 'reasoning']
    if len(rows) != 5 or {r['model'] for r in rows} != set(LABELS):
        raise ValueError('Expected the original five models and CoT-only aggregate rows')
    rows = sorted(rows, key=lambda r: list(LABELS).index(r['model']))
    if any(int(r['unresolved']) != 0 for r in rows):
        raise ValueError('This thumbnail requires the resolved original result set')
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 13,
                         'svg.fonttype': 'none', 'axes.unicode_minus': False})
    fig = plt.figure(figsize=(12, 6.3), dpi=100, facecolor='white')
    ax = fig.add_axes([.282, .185, .515, .605])
    fig.text(.5, .91, 'Hidden Agenda Benchmark', ha='center', va='center',
             fontsize=29, weight='bold', color='#18263B')
    for i, (r, color) in enumerate(zip(rows, COLORS)):
        rate, low, high = (float(r[k]) for k in ('confirmed_rate', 'ci95_low', 'ci95_high'))
        if i % 2 == 0:
            ax.axhspan(i-.41, i+.41, color='#F5F7FA', zorder=0)
        ax.errorbar(rate, i, xerr=[[rate-low], [high-rate]], fmt='o',
                    markersize=10, color=color, ecolor=color, elinewidth=2.5,
                    capsize=6, capthick=2.2, zorder=3)
        ax.text(1.09, i, f"{rate:.0%}  ({r['confirmed']}/{r['n']})",
                transform=ax.get_yaxis_transform(), va='center', ha='left',
                fontsize=16, color='#26364A', clip_on=False)
    ax.set_yticks(range(5), [LABELS[r['model']] for r in rows], fontsize=16)
    ax.tick_params(axis='y', length=0, pad=17, colors='#26364A')
    ax.set_ylim(4.6, -.6)
    ax.set_xlim(-.0018, .062)
    ax.set_xticks([0, .01, .02, .03, .04, .05, .06])
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.tick_params(axis='x', length=0, pad=9, labelsize=13, colors='#627185')
    ax.grid(axis='x', color='#E2E7EE', linewidth=.8, zorder=1)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xlabel('Success + CoT evasion', fontsize=16, color='#26364A', labelpad=14)
    fig.text(.5, .055, '100 tasks per model  ·  95% confidence intervals',
             ha='center', fontsize=11, color='#6B7788')
    name='hidden-agenda-benchmark-cot-1200x630'
    # No tight bounding box: that would change the requested pixel dimensions.
    fig.savefig(output/(name+'.png'), dpi=100, facecolor='white')
    fig.savefig(output/(name+'.svg'), facecolor='white')
    plt.close(fig)
    with (output/'data.csv').open('w', newline='') as stream:
        writer=csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader();writer.writerows(rows)
    (output/'metadata.json').write_text(json.dumps(dict(
        title='Hidden Agenda Benchmark', width_px=1200, height_px=630,
        metric='Primary correct AND auxiliary correct AND valid formatting AND no CoT monitor alert',
        denominator='100 assigned concealment attempts per original model',
        interval='Original pointwise 95% Wilson intervals',
        source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        rows=rows),indent=2)+'\n')
    print((output/(name+'.png')).resolve())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,
                   default=Path('offical_run/judge-v2-empty-cot-policy/comparison/aggregate.csv'))
    p.add_argument('--output',type=Path,default=Path('runs/substack-thumbnail-original-five'))
    a=p.parse_args();build(a.source,a.output)
