import importlib.util
from pathlib import Path


def module(name='prepare_training_pairs'):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[1] / f'scripts/phase2/{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_disjoint_balanced_reproducible_pairs():
    m = module()
    coding = [dict(task_id=str(i), prompt=f'code{i}') for i in range(5)]
    math = [dict(question=f'question {i}', answer=f'work\n#### {i}') for i in range(12)]
    math += [dict(question='Question 1!', answer='#### 1'),
             dict(question='invalid numeric answer', answer='#### one')]
    args = (coding, math, {'0', '1'}, {m.normalized('question 0')}, 10, 42)
    pairs = m.build_pairs(*args)
    assert pairs == m.build_pairs(*args)
    assert {p['primary_id'] for p in pairs} == {'2','3','4'}
    assert len({m.normalized(p['auxiliary']) for p in pairs}) == 10
    assert m.normalized('question 0') not in {m.normalized(p['auxiliary']) for p in pairs}
    counts = [sum(p['primary_id'] == i for p in pairs) for i in ('2','3','4')]
    assert max(counts) - min(counts) <= 1


def test_mbpp_structural_duplicates_and_primary_prompt():
    m = module('prepare_mbpp_pairs')
    reference = dict(task_id='HumanEval/0', prompt='def original(x):\n    """spec"""\n',
                     canonical_solution='    return x + 1\n', entry_point='original')
    def row(i, code):
        return dict(task_id=i, text='Return the input length.', code=code,
                    test_list=['assert length([1]) == 1'], test_setup_code='')
    rows=[row(601,'def duplicate(y):\n    return y + 1'),
          row(602,'def length(items):\n    # PRIVATE REFERENCE SENTINEL\n    return len(items)'),
          row(603,'def length_again(xs):\n    return len(xs)'),
          row(511,'def other_length(z):\n    return len(z)'),
          row(512,'def squared(z):\n    return z * z')]
    eligible, excluded=m.coding_candidates(rows,[reference])
    assert [r['primary_id'] for r in excluded]==['MBPP/601']
    chosen, rejected=m.select(eligible,1,1,7)
    assert chosen['validation'][0]['primary_id']=='MBPP/512'
    assert len(chosen['training'])==1
    prompt=chosen['training'][0]['primary']
    assert 'PRIVATE REFERENCE SENTINEL' not in prompt
    assert 'return len(' not in prompt
    assert 'Public example:' in prompt
    assert 'def ' in prompt
    assert any(r['reason']=='structural_duplicate_in_selected_data' for r in rejected)


def test_mbpp_fingerprint_keeps_operations_and_builtin_names():
    m=module('prepare_mbpp_pairs')
    fp=lambda code:m.body_fingerprint(m.parse(code).body[0])
    assert fp('def a(x):\n    return len(x)') == fp('def b(y):\n    return len(y)')
    assert fp('def a(x):\n    return len(x)') != fp('def a(x):\n    return sum(x)')
    assert fp('def a(x):\n    return x + 1') != fp('def a(x):\n    return x - 1')
