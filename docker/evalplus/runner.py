"""Trusted orchestration; generated code runs only in EvalPlus child processes."""
import json
import sys
from evalplus.eval import PASS, untrusted_check
from evalplus.gen.util import trusted_exec


def main():
    request = json.load(sys.stdin)
    problem = request['problem']
    reference = problem['prompt'] + problem['canonical_solution']
    results = {}
    for group in ('base', 'plus'):
        inputs = problem[group + '_input']
        expected, reference_times = trusted_exec(reference, inputs, problem['entry_point'], record_time=True)
        status, details = untrusted_check('humaneval', request['solution'], inputs,
            problem['entry_point'], expected=expected, atol=problem['atol'],
            ref_time=reference_times, fast_check=True, min_time_limit=1, gt_time_limit_factor=4)
        results[group] = dict(status=status, success=status == PASS, tests=len(inputs),
                              evaluated=len(details))
    print(json.dumps(dict(success=all(r['success'] for r in results.values()),
                         status='graded', groups=results)))

if __name__ == '__main__':
    main()
