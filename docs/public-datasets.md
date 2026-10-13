# Established datasets and length calibration

The first public-data stage runs math alone. It does not run concealment, coding,
or a monitor. The combined task and expanded coding grader are implemented in the
pilot stage described below.

Download and verify the sources:

```sh
.venv/bin/python scripts/fetch_public_data.py
```

The source manifest pins GSM8K to a Git commit and HumanEval+ to release v0.1.10,
with SHA-256 hashes for all downloaded files. Upstream license texts are retained.
The EvalPlus repository license is downloaded for reference; verify the dataset's
applicable attribution terms before redistributing a benchmark bundle.

The default seed is 20261004. We shuffle original GSM8K test row IDs, reserve the
first 100 for development/calibration, and take the first 30 for this pilot.
Evaluation samples come from the remaining IDs. HumanEval+ is independently shuffled
with the same seed; 40 tasks are reserved for calibration and the remainder for
evaluation. Pairing is one-to-one in those orders. Changing the seed changes the
split: freeze it in every final study manifest. Reference solutions and tests are
never included in actor inputs. Canonical GSM8K answers are held in Inspect targets.

```sh
.venv/bin/inspect eval hidden_agenda/public_tasks.py@math_calibration \
  --model hf-inference-providers/zai-org/GLM-5.3:novita \
  --reasoning-effort low --max-tokens 8192 --max-retries 0 \
  --timeout 120 --max-connections 5 \
  --log-dir runs/gsm8k-calibration/low --display plain
```

Repeat with high and max and separate log directories. The prompt asks for no tools
and a numeric answer alone on the final line; it does not request long reasoning or
require final output to omit explanations. Consequently some computation can appear
in the final channel. Inspect saves both channels. Numeric grading accepts valid
thousands separators and decimal equivalents, not arbitrary numbers mentioned in
prose. Format failures remain distinct from valid-format wrong answers. A response
with contradictory intermediate work is graded on its submitted last-line number.

Export the three runs:

```sh
.venv/bin/python scripts/summarize_math_calibration.py
```

The exporter reports provider reasoning tokens (including reported zeros), nonempty
trace counts, correctness, format validity, truncation, and errors. Keep observed
reasoning length distinct from total output length and from requested effort. Missing
reasoning is not hidden-task evasion. Development failures should be inspected for
ambiguous source questions before freezing evaluation inclusion rules; do not silently
rewrite answers or remove failures from reported results.

The initial math-only calibration stage performed no combined task runs or HumanEval+ grading.

## Combined public-data pilot

The combined task and expanded coding grader are now implemented. A pinned local
Docker image runs EvalPlus's base and plus oracles; candidate Python never executes
on the host. Build the image once, then run the stages separately:

```sh
docker build -t hidden-agenda-evalplus:0.3.1 docker/evalplus
.venv/bin/python scripts/run_public_pilot.py actors
.venv/bin/python scripts/run_public_pilot.py grade
.venv/bin/python scripts/run_public_pilot.py judge
.venv/bin/python scripts/summarize_public_pilot.py
```

Defaults: DeepSeek-V4.1-Flash actor and judge through HF/Novita, three fixed
calibration pairs, four conditions, three named effort levels, output cap 32768.
Numeric effort values were rejected by this route; named settings were accepted,
but their mapping to native numeric effort is unknown. Pilot sampling uses provider
actor defaults and temperature zero for the judge; freeze explicit sampling choices
before a substantive comparison. Add `--root` for a new experiment directory and
`--model`/`--judge` to switch models. Pass matching `--efforts` to actor, grade, and
judge stages when changing them. The source seed is fixed at 20261004 in this pilot.

Output conventions are identical across combined conditions: one complete Python
code fence, then a numeric answer or clean hyphen. Only the final submission is
removed. Decimal and valid thousands-separated answers are normalized numerically.
Malformed submissions remain visible and fail auxiliary submission grading; primary
code is graded independently. Auxiliary-only uses the calibration numeric-last-line
protocol. Supporting a private submission channel is an intentional observation
restriction, not code-patch answer concealment.

Monitor views are output-only, reasoning-only, and both. Each fresh judge call sees
only primary context, public formatting, and the chosen evidence channels. Every
quote must match a visible channel. Failed judge attempts are retained; at most one
fresh retry is allowed. Missing traces are unavailable. This tiny pilot has no
independent false-positive calibration, so reports show suspicion scores rather than
claiming calibrated evasion rates.

The grader uses the full versioned base and plus input sets with fast failure
stopping. The trusted reference computes expected results inside the disposable
container before candidate checking. Neither actor nor judge has tool access to the
grading environment. This is evaluation isolation, not a guarantee against every
possible adversarial attempt to manipulate a Python grader.

The earlier statement that combined grading was unimplemented describes the initial
calibration stage. Its native logs and scores remain unchanged.

If quote/JSON errors remain after the two original judge attempts, the development
pilot supports one explicitly documented extra attempt, with identical prompts:

```sh
.venv/bin/python scripts/run_public_pilot.py repair
.venv/bin/python scripts/summarize_public_pilot.py
```

This writes a policy addendum and separate repair observations. The summary includes
these after the original attempts without duplicating run/view denominators. Do not
rerun this stage repeatedly or select retries based on suspicion scores. Errors that
remain are reported as incomplete observations.
