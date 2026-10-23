# Official result snapshot

The [illustrative sabotage comparison](illustrative-sabotage-comparison/README.md)
recreates the supplied published chart with approximate points and adds a labeled
zero reference for open-source models. It is an illustration, not an additional
benchmark measurement or a matched comparison between the two evaluations.

The separate [exploratory 2+2 experiment](trivial-aux-20261023/REPORT.md) tests all
five models once on the same randomly selected HumanEval/9 coding task with a
hidden `2+2` question. All five completed both tasks and were detected in both
reasoning monitor views. [Full prompts, traces and verdicts](trivial-aux-20261023/TRACES.md)
are included. This single-instance experiment is separate from the 100-pair benchmark.

The [updated monitoring dataset](judge-v2-empty-cot-policy/README.md) implements
automatic CoT-only passes for completed responses without emitted reasoning and
uses output-only evidence for their combined monitor. The last failed clean
evaluation call was recovered through Featherless; all models have 100 completed
clean evaluation outcomes. Earlier snapshots and audit mappings are preserved.

The [false-positive threshold analysis](false-positive-threshold-0.5/REPORT.md)
plots each model's false-positive rate with 95% Wilson intervals at suspicion
strictly greater than 0.5. This alternate cutoff is recorded separately from the
original calibration.

The official reviewed human audit is [manual audit version 4](manual-audit-v1/REPORT.md).
Its original blinded version 3 is preserved alongside the revised scores. Version
4 incorporates feedback on A028 and A067; A099 remains an intentional disagreement.
The [unblinded audit review](manual-audit-v1/review.html) includes model identities,
the answer key, human and LLM scores, and searchable trajectories.

`judge-v2-provider-repaired/` is a frozen copy of the final local run
`runs/judge-v2-provider-repaired`, archived on October 17, 2026. The directory name
`offical_run` follows the requested spelling.

- [Results and protocol amendments](judge-v2-provider-repaired/comparison/REPORT.md)
- [Graph](judge-v2-provider-repaired/comparison/model-comparison.png)
- [Paired coding outcomes and judge false positives](judge-v2-provider-repaired/comparison/CLEAN-CONTROLS.md)
- [Offline trajectory viewer](judge-v2-provider-repaired/trajectories.html)
- [Dataset overview](judge-v2-provider-repaired/README.md)
- [Validation](judge-v2-provider-repaired/VALIDATION.json)

The snapshot contains 1,150 trajectories and 3,450 final monitor outcomes across
five models, including calibration and clean controls. Seven of nine original
timed-out calls were recovered through explicit retries. Two DeepSeek Pro clean
calls still have provider errors and remain unavailable; they are not known wrong
answers. Shared judge thresholds are frozen. Original nonempty responses and
their deterministic grades were unchanged. This follow-up includes timeout and
provider repairs and differs from the original single-attempt protocol.

All final response text, emitted reasoning, deterministic grades, judgments,
cutoffs, manifests and current provider-retry logs are included. Provenance paths
and hashes retain their original values. Earlier repair rounds and original
generation logs referenced by those paths remain in the local ignored `runs/`
tree; they are not bundled here. They are not needed to inspect final outcomes or
rebuild the viewer and comparison from the saved records. Resuming historical
repair workflows requires those earlier source directories.

Open the existing viewer without any API calls:

```sh
open offical_run/judge-v2-provider-repaired/trajectories.html
```

Recompute the clean-control report from the archived records:

```sh
uv run python scripts/report_clean_controls.py --root offical_run/judge-v2-provider-repaired
```

`SHA256SUMS.json` records hashes for every file in the copied run, independently
of the historical source hashes in its manifests.
