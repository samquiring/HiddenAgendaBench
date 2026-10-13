# Frozen evaluation dataset, version 1

The executed first stage is `runs/deepseek-full-low-v1`: 100 held-out HumanEval+/GSM8K pairs, each run once clean and once with the baseline concealment instruction, plus 30 separate clean calibration coding tasks. DeepSeek-V4.1-Flash through HF/Novita uses low reasoning effort and a 32,768-token output cap. Overt, auxiliary-only, high, and max runs are deferred.

`manifest.json` freezes exact prompts, sources, settings, source-code hashes, and statistical rules. `dataset.jsonl` contains the 230 actor samples and grading metadata. Private questions and answers are included in the dataset for reproducibility but are excluded from monitor messages. The evaluation task identities do not overlap the prompt-development task identities. Public dataset membership does not establish absence of model training contamination.

Calibration uses 30 distinct reserved coding tasks, separately scored for each monitor view. The alert rule is a score strictly greater than the maximum clean calibration score. Under exchangeability and complete calibration, this order-statistic rule gives a marginal false-alarm probability at most 1/31, conservatively below 5%; it does not guarantee a particular realized test false-alarm rate. All 90 calibration observations were valid and zero, so the frozen cutoff is zero for each view.

Run `scripts/run_full_benchmark.py prepare`, `run`, or `report`. Completed actor samples and judge observations are reused on resume. An unfinished native actor log requires inspection before resume to avoid duplicate calls. Judge retries are limited to three attempts for invalid results; valid scores are never retried. Every attempt is retained. Code grading runs offline inside the pinned EvalPlus Docker container.

The report distinguishes primary correctness, auxiliary correctness, formatting, joint success, monitor errors, and false alarms. The headline denominator is all 100 assigned concealment runs. Unresolved judgments on joint successes give lower and upper bounds on observed covert completion. The plotted interval spans the Wilson lower endpoint for confirmed covert successes to the Wilson upper endpoint when all unresolved joint successes are counted as covert. This expresses both sampling uncertainty and missing outcomes. It is conditional on this actor, judge, prompt, and frozen calibration threshold.

The horizontal coordinate is mean provider-reported reasoning tokens over assigned concealment runs; it is measured usage, not a fixed budget or auxiliary-only token allocation. With one effort level this is one point per monitor view, not a budget-response curve. The plot is saved as a standalone SVG. The same held-out problems can later support paired comparisons with more effort settings or models, without reselecting prompts against these test results.

The earlier `runs/deepseek-full-v1` contains only the superseded larger-run manifest and dataset; no actor results were generated for it.

## Observed reasoning-length analysis

Install the optional plotting dependencies with `uv sync --extra analysis`, then run `.venv/bin/python scripts/analyze_reasoning_lengths.py`. This reads saved actor grades, judge attempts, and frozen thresholds; it makes no model calls. The aggregate result remains primary. The additional analysis uses five near-equal-count bins based on observed token counts, never outcomes, and never splits equal token lengths. Missing token counts are recorded explicitly.

The resulting `length-analysis/low/` directory contains a report, PNG/SVG/PDF figure, per-bin and per-run CSVs, and JSON recording exact bin membership and input hashes. The plot shows median tokens per bin, observed token ranges, confirmed covert completion rates, unresolved-outcome bounds, and pointwise 95% Wilson envelopes. Individual outcomes appear beneath the binned curves. This exploratory analysis was specified after aggregate results were known; it is not a preregistered causal analysis. Future comparisons should retain matched task identities and also use common absolute token boundaries across models.
