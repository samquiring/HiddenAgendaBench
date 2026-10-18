"""Build an unblinded, searchable review page for a completed human audit."""
import argparse
import hashlib
import json
from pathlib import Path


def build_review(key_path, scores_path, output):
    key=json.loads(Path(key_path).read_text())
    scores=json.loads(Path(scores_path).read_text())
    if key['batch_id']!=scores['batch_id'] or key['view']!=scores['view']:
        raise ValueError('Scores and answer key belong to different audit batches')
    if set(scores['scores'])!={c['audit_id'] for c in key['cases']}:
        raise ValueError('Scores do not match the assigned audit case IDs')
    cases=[]
    for case in key['cases']:
        record=case['record']
        label=record['actor'].split('/',1)[-1].rsplit(':',1)[0].split('/')[-1]
        cases.append(dict(**case,human=scores['scores'][case['audit_id']],model_label=label))
    bundle=dict(batch_id=key['batch_id'],view=key['view'],cases=cases,
                scores_sha256=hashlib.sha256(Path(scores_path).read_bytes()).hexdigest())
    payload=json.dumps(bundle,ensure_ascii=True).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=(Path(__file__).parent/'resources/manual_audit_review.html').read_text()
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(template.replace('__REVIEW_DATA__',payload))
    print(f'{output}: {len(cases)} unblinded cases, with human scores and LLM judgments')
    return bundle


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key',type=Path,default=Path('offical_run/manual-audit-v1/PRIVATE-answer-key.json'))
    parser.add_argument('--scores',type=Path,default=Path('offical_run/manual-audit-v1/scores-v4-official.json'))
    parser.add_argument('--output',type=Path,default=Path('runs/manual-audit-v1/review.html'))
    args=parser.parse_args()
    build_review(args.key,args.scores,args.output)
