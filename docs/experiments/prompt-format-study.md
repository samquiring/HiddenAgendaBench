> Historical development documentation. The default workflow is described in [the main README](../../README.md).

# Development prompt and format study

Run `scripts/experiments/run_prompt_study.py` with stages `actors`, `grade`, `judge`, and `summarize`, in that order. The default output directory is `runs/deepseek-prompt-format-study`.

This bounded experiment uses ten matched HumanEval+/GSM8K development pairs, DeepSeek-V4.1-Flash through Hugging Face/Novita, low reasoning effort, and a 32,768-token output cap. It compares three concealment instructions (baseline, brief Python-focused reasoning, and no restatement of private instructions) with three submission formats (fenced code and numeric last line, fenced code and XML answer field, and a JSON object containing code and an answer string). Each format also has ten clean primary-only controls: 120 actor runs total.

Exact actor inputs and source checksums are frozen in the manifest before generation. There is no judge identity or feedback given to the actor. The fixed monitor scores three views of each saved trajectory: output, emitted reasoning, and both. Up to three calls are allowed for invalid monitor JSON/schema/evidence quotes; every attempt is retained. Valid judgments are never retried to change their scores.

The answer submission is removed uniformly from clean and concealment final responses; reasoning is never redacted. JSON code is converted to a Python fence only for deterministic grading, while the monitor receives the redacted JSON artifact. Primary success is checked with pinned EvalPlus tests inside disposable offline Docker containers. Numeric answers are compared independently against GSM8K targets. Malformed submissions cannot count as covert completion.

The 0.5 suspicion threshold is an exploratory development cutoff, not a calibrated false-positive operating point. Ten matched problems per cell do not establish population-level limits, and the nine concealment variants are not 90 independent problems. Prompt selection here must be followed by held-out evaluation and separate clean threshold calibration.
