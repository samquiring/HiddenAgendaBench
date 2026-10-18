import json

import pytest

from hidden_agenda.manual_audit_review import build_review


def test_review_joins_scores_and_reveals_key_safely(tmp_path):
    key=dict(batch_id='batch',view='reasoning_output',cases=[dict(audit_id='A001',
        record=dict(actor='hf-inference-providers/vendor/model:provider',primary='</script><script>bad()</script>',
                    auxiliary='Private math question',answer='42'),selection=['random_sample'],judgments=[])])
    scores=dict(batch_id='batch',view='reasoning_output',scores={'A001':dict(suspicion=0.9)})
    kp=tmp_path/'key.json';sp=tmp_path/'scores.json';kp.write_text(json.dumps(key));sp.write_text(json.dumps(scores))
    bundle=build_review(kp,sp,tmp_path/'review.html')
    assert bundle['cases'][0]['human']['suspicion']==0.9
    assert bundle['cases'][0]['model_label']=='model'
    html=(tmp_path/'review.html').read_text()
    assert 'Private math question' in html and '"answer": "42"' in html
    assert '</script><script>bad()' not in html
    assert '\\u003c/script\\u003e' in html
    scores['batch_id']='other';sp.write_text(json.dumps(scores))
    with pytest.raises(ValueError,match='different audit batches'):
        build_review(kp,sp,tmp_path/'bad.html')
    scores['batch_id']='batch';scores['scores']={'A002':{}};sp.write_text(json.dumps(scores))
    with pytest.raises(ValueError,match='case IDs'):
        build_review(kp,sp,tmp_path/'bad.html')
