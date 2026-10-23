# Screenshot recreation

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
