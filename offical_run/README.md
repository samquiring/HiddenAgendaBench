# Official result snapshot

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
