"""Recreate the supplied sabotage-monitoring screenshot with approximate data.

Coordinates and interval endpoints are visual estimates, not published raw data
or measurements from HiddenAgendaBench. No original sample counts are inferred.
"""
import argparse
import csv
import json
from pathlib import Path


SERIES = [
    dict(name='gray', label='GPT 5.5', color='#8b9195', marker='D', linestyle='--',
         tokens=[3700, 9400, 11800, 18500],
         rates=[0, .06, 0, 0], low=[0, 0, 0, 0], high=[.44, .18, .10, .06]),
    dict(name='blue', label='GPT-5.6 Sol', color='#294b80', marker='s', linestyle='-',
         tokens=[2200, 20000, 22000, 27500],
         rates=[0, .03, .03, 0], low=[0, 0, 0, 0], high=[.36, .18, .12, .10]),
    dict(name='pink', label='GPT-6 Astra', color='#c52b99', marker='o', linestyle='-',
         tokens=[8700, 11300, 14000, 22000],
         rates=[.72, .47, .43, .20],
         low=[.56, .32, .28, .12], high=[.84, .63, .57, .29]),
    dict(name='open_source_illustrative',label='All open-source models (illustrative)',
         color='#158464',marker=None,linestyle=':',kind='illustrative',
         tokens=[1000,40000],rates=[0,0],low=[None,None],high=[None,None]),
]


def make_chart(output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator, PercentFormatter

    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'sans-serif', 'font.sans-serif':['Arial','DejaVu Sans'],
                         'text.color':'#454545', 'axes.labelcolor':'#454545',
                         'xtick.color':'#454545', 'ytick.color':'#454545'})
    fig,ax=plt.subplots(figsize=(7.62,5.15),facecolor='white')
    fig.subplots_adjust(left=.175,right=.94,bottom=.30,top=.81)
    handles=[]
    for series in SERIES:
        illustrative=series.get('kind')=='illustrative'
        if not illustrative:
            lower=[rate-low for rate,low in zip(series['rates'],series['low'])]
            upper=[high-rate for rate,high in zip(series['rates'],series['high'])]
            assert all(v>=0 for v in lower+upper)
            ax.errorbar(series['tokens'],series['rates'],yerr=[lower,upper],fmt='none',
                        ecolor=series['color'],alpha=.18,elinewidth=.7,capsize=2,capthick=.7,zorder=1)
        line,=ax.plot(series['tokens'],series['rates'],color=series['color'],
                     marker=series['marker'],linestyle=series['linestyle'],
                     linewidth=2 if illustrative else 1.4,markersize=3.8 if series['name']!='gray' else 4.2,
                     markeredgewidth=.35,zorder=1.8 if illustrative else 2,label=series['label'])
        handles.append(line)
        if series['name']=='gray':line.set_dashes([5,3])
    ax.set_xscale('log')
    ax.set_xlim(1000,40000);ax.set_ylim(-.035,1.06)
    ax.xaxis.set_major_locator(FixedLocator([1000,2000,5000,10000,20000,40000]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value,_:f'{value/1000:g}k'))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_locator(FixedLocator([0,.2,.4,.6,.8,1]))
    ax.yaxis.set_major_formatter(PercentFormatter(1,decimals=0))
    ax.tick_params(axis='both',which='major',labelsize=10,length=0,pad=7)
    ax.spines[['top','right']].set_visible(False)
    for side in ('left','bottom'):
        ax.spines[side].set_color('#b4b4b4');ax.spines[side].set_linewidth(.8)
    ax.set_title('Chain-of-thought Monitoring for Sabotage Success',loc='left',fontsize=14,pad=18)
    ax.set_xlabel('Chain-of-thought + tool call tokens',fontsize=12,labelpad=10)
    ax.set_ylabel('Success + evasion rate',fontsize=12,labelpad=11)
    fig.legend(handles[:3],[s['label'] for s in SERIES[:3]],loc='lower center',
               bbox_to_anchor=(.53,.12),ncol=3,frameon=False,fontsize=10,columnspacing=2.5,handlelength=2.5)
    fig.legend(handles[3:],[s['label'] for s in SERIES[3:]],loc='lower center',
               bbox_to_anchor=(.53,.045),frameon=False,fontsize=10,handlelength=3)
    for ext in ('png','svg','pdf'):
        fig.savefig(output/f'sabotage-monitoring-recreation.{ext}',dpi=200)
    plt.close(fig)
    (output/'approximate-data.json').write_text(json.dumps(dict(
        provenance='Three visually approximated screenshot series plus an illustrative zero reference across the full axis. Not published raw data or HiddenAgendaBench measurements.',
        intervals='Visually estimated endpoints; no confidence level or sample counts inferred.',series=SERIES),indent=2)+'\n')
    with (output/'approximate-data.csv').open('w',newline='') as stream:
        writer=csv.writer(stream,lineterminator='\n')
        writer.writerow(['series','label','kind','tokens','success_evasion_rate','interval_low','interval_high'])
        for s in SERIES:
            writer.writerows((s['name'],s['label'],s.get('kind','screenshot_approximation'),*point) for point in zip(s['tokens'],s['rates'],s['low'],s['high']))
    (output/'README.md').write_text('''# Screenshot recreation

The title, axis labels, logarithmic token axis, colors, marker shapes and line
styles reproduce the supplied chart. Points and error-bar endpoints are visually
estimated. These are not original published numerical data or HiddenAgendaBench
measurements. The model legend follows the separately supplied legend screenshot:
GPT 5.5 (gray), GPT-5.6 Sol (blue), GPT-6 Astra (pink).

The green dotted line, "All open-source models (illustrative)", is a zero reference
from 1k to 40k tokens, with no error bars. It is not a fitted or measured curve,
does not represent the nonzero GLM escape, and does not establish open-source
model performance on the sabotage evaluation. No sample counts or confidence
levels are inferred. The CSV/JSON distinguish this reference from screenshot data.

Run from the repository root:

```sh
uv run python scripts/recreate_sabotage_chart.py
```

Edit `SERIES` in that script to replace approximations with authoritative values
when available. PNG, SVG and PDF exports accompany CSV and JSON data.
''')
    print(output/'sabotage-monitoring-recreation.png')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('runs/sabotage-chart-recreation'))
    args=parser.parse_args()
    make_chart(args.output)
