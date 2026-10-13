# Hidden Agenda Benchmark

A Python / Inspect AI pilot measuring whether models can solve an unrelated auxiliary problem during legitimate work without a judge detecting it. See [protocol](docs/design.md) and [framework decision](docs/frameworks.md).

## Setup

```sh
uv sync --extra dev --python 3.12
source .venv/bin/activate
pytest
python -m hidden_agenda.cli preview --size 5
```

Set `OPENROUTER_API_KEY` in your environment. Select real accessible model IDs explicitly, e.g. `openrouter/<provider>/<model>`. For LiteLLM proxy use `litellm-proxy/<deployment>` and `LITELLM_PROXY_BASE_URL` / `LITELLM_PROXY_API_KEY`. Inspect also supports native providers. Do not commit credentials.

## Actor → export → grade → judge

```sh
python -m hidden_agenda.cli run --model "$ACTOR_MODEL" --condition concealment --split dev --count 3 --epochs 2 --size 5 --max-tokens 4096
python -m hidden_agenda.cli export logs/ACTUAL_LOG.eval --trace-kind emitted --output actors.jsonl
# Start Docker and prepare the grading image once:
docker pull python:3.12-slim
python -m hidden_agenda.cli grade actors.jsonl --output graded.jsonl
python -m hidden_agenda.cli judge graded.jsonl --model "$JUDGE_MODEL" --output judgments.jsonl
inspect view
```

Actor has no tools. Docker is only used after generation to grade code. Confirm the provider exposes emitted reasoning before choosing `--trace-kind emitted`; use `summary` or `unavailable` otherwise. No particular model is assumed to expose traces. Optional `--reasoning-effort low|medium|high` is passed to Inspect; supported values depend on backend. Keep actual resolved configuration and provider routing fixed for comparisons.

Repeat actor runs with `clean`, `auxiliary_only`, and `overt` conditions. Auxiliary-only needs no code grading and is skipped by monitors. Inspect epochs are independent repetitions with no judge feedback. Outputs use exclusive creation to avoid overwriting previous experiments.

## Calibration and held-out scoring

Generate clean runs with `--split calibration`, export, grade and judge them. Freeze thresholds before examining test results:

```sh
python -m hidden_agenda.cli calibrate calibration-judgments.jsonl --fpr 0.05 --output thresholds.json
python -m hidden_agenda.cli report test-judgments.jsonl --thresholds thresholds.json
```

Every calibrated view must have valid judgments; for output-only experiments select only output rows in a separate file. Reports reject mismatched calibration groups and non-test data. Preserve all assigned records, including errors. Never interpret unavailable reasoning as successful concealment. Record all conditions and aggregate task success from graded actor exports, including the auxiliary-only baseline. Judge task-identification text is collected for manual grading; the report currently covers detection, not identification accuracy.

This is a runnable experimental scaffold with small fixtures, not a validated benchmark suite. Templates, task difficulty, uncertainty estimates and model selection need expansion before substantive rankings. Native Inspect logs and actor exports contain private prompts and answers; judge payloads are built with an explicit allowlist.
# Channel controllability diagnostic

Established task sources and math-only calibration are documented in
[public datasets](docs/public-datasets.md). The initial GLM calibration results are in
[the calibration report](runs/gsm8k-calibration/REPORT.md).

The `hidden-agenda control` command tests lowercase, alternating case, and forbidden-word
restrictions on reasoning and final responses, with an unrestricted baseline.
See [setup, scoring, and reasoning-effort comparisons](docs/channel-control.md).

## Frozen public-task evaluation and reasoning lengths

The [100-pair evaluation design](docs/full-dataset.md) documents the completed
DeepSeek low-effort baseline, independent clean calibration, and observed-length analysis.
See the [aggregate report](runs/deepseek-full-low-v1/REPORT.md) and
[five-bin length report](runs/deepseek-full-low-v1/length-analysis/low/REPORT.md).
To reproduce the length plots from saved responses, install `.[analysis]` and run:

```sh
python scripts/analyze_reasoning_lengths.py
```

This generates PNG, SVG, PDF, and CSV artifacts without additional model calls.
