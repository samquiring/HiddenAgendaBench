from hidden_agenda.public_tasks import numeric, grade_math


def test_numeric_grading():
    assert grade_math('It totals 1200.\n1,200', '1200') == dict(correct=True, format_valid=True)
    assert grade_math('4\nActually 5', '4') == dict(correct=False, format_valid=False)
    assert not grade_math('5', '4')['correct']
    assert numeric('1,2') is None
    assert numeric('NaN') is None
