# Configuring a model run

The default dataset and protocol are fixed: 100 evaluation pairs, 30 distinct clean calibration tasks, clean and concealment conditions, and three monitor views. Every configuration uses the same deterministic task assignments. Start a new results directory to change models or settings.

| TOML setting | Default | Meaning |
|---|---|---|
| `actor` | DeepSeek-V4.1-Flash via HF/Novita | Inspect model identifier for task generation |
| `judge` | Same fixed DeepSeek model | Monitor model, independent of the actor selection |
| `effort` | `low` | Actor reasoning effort; `none` omits the parameter |
| `judge_effort` | `low` | Judge effort; `none` omits the parameter |
| `max_tokens` | 32768 | Actor output cap, including provider-counted reasoning |
| `judge_max_tokens` | 8192 | Judge output cap |
| `actor_connections` | 6 | Concurrent actor requests |
| `judge_workers` | 12 | Concurrent isolated judge calls |
| `judge_attempts` | 3 | Maximum attempts to obtain a schema-valid, quote-valid judgment |
| `actor_args`, `judge_args` | `stream = false` | Additional Inspect model/provider arguments |

Use environment variables for API credentials, never TOML provider arguments: the latter are written into the public run manifest. Unsupported configuration keys and invalid counts are rejected. Provider-specific options, model availability, and supported reasoning levels must be checked for the chosen backend. A model accepting an effort label does not establish an identical compute allocation across providers.

`prepare --config ... --root ...` writes an immutable manifest and dataset without model calls. `run --root ...` uses that manifest. Passing a conflicting config to an existing run is an error. Regenerating reports and plots only reads saved observations and frozen thresholds; it does not create a run or invoke a model.

The default source directory is `data/sources` under the current working directory. Set `HIDDEN_AGENDA_DATA_DIR` in the shell before invoking the CLI to use another location. Source URLs and expected hashes are bundled with the Python package. Downloads never silently select a newer dataset revision.

Calibration must have all 30 valid judgments for every view before evaluation starts. Invalid judgments retain every bounded retry; successful judgments are never retried to improve their score. Incomplete calibration stops the run rather than silently assigning an uncalibrated threshold. A failed or unfinished actor run is retained for inspection rather than automatically reissued.

An explicit alternative for cross-actor comparisons is `hidden-agenda run --root runs/new-model --calibration-from runs/reference-model`. This transfers an already frozen complete calibration from the same judge and judge generation settings, records the source and threshold-file hash in `calibration-transfer.json`, and must be selected before any target evaluation responses exist. It leaves the target calibration observations intact. On resume the recorded source is reused automatically. The reference calibration's false-positive guarantee does not automatically transfer to a different actor distribution: report the target clean-control results and all unresolved observations. This is a documented protocol amendment, not the default automatic fallback for calibration failures.

For comparable model results, keep task identities, prompt, judge configuration, output cap, grading environment and monitored views fixed. Report actual token usage and missing-trace coverage. Different model tokenizers and reasoning-effort labels complicate comparisons. The five quantile bins are descriptive within each model; use common absolute token ranges as well when comparing multiple models. Do not tune prompts on the held-out set.
