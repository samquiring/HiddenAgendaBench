# Repaired benchmark follow-up

This follows `../judge-v2-uniform`: nine original calls hit a 240-second time limit. One retry at original settings recovered four responses. A second round with a 600-second request timeout and 900-second sample limit recovered three more. Two remaining DeepSeek Pro clean calls were retried through DeepInfra and still returned provider errors (HumanEval/132 calibration; HumanEval/145 evaluation). They remain unavailable. No nonempty answer or formatting failures were retried.

All normal original responses and grades are unchanged. New responses were graded in Docker and judged using v2 with the original shared cutoffs. The original data and every repair round remain preserved. Actor retry plans/manifests record timeout/provider overrides and previous rounds. This is a follow-up with explicit retries, not the original single-attempt protocol.

- [Paired coding results and judge false-positive rates](comparison/CLEAN-CONTROLS.md)
- [Aggregate benchmark results](comparison/REPORT.md)
- [Graph](comparison/model-comparison.png)
- [Trajectory viewer](trajectories.html)
- [Validation](VALIDATION.json)
