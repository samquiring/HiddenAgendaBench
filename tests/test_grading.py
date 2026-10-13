import subprocess
from types import SimpleNamespace
import pytest
from hidden_agenda.grading import grade_python


def test_container_grading_boundary(monkeypatch):
    def execute(command, **kwargs):
        assert "--network=none" in command
        assert "--read-only" in command
        assert "--cap-drop=ALL" in command
        assert "expected" not in kwargs["input"]
        return SimpleNamespace(returncode=0, stdout="[[1, 2]]", stderr="")
    monkeypatch.setattr(subprocess, "run", execute)
    assert grade_python("```python\ndef solve(xs): return xs\n```", [[1, 2]], [[1, 2]])["success"]
    assert not grade_python("```python\ndef solve(xs): return xs\n```", [[1, 2]], [[3]])["success"]


def test_infrastructure_error_not_task_failure(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=125, stderr="daemon down"))
    with pytest.raises(RuntimeError, match="infrastructure"):
        grade_python("```python\ndef solve(xs): return xs\n```", [], [])


def test_timeout_removes_container(monkeypatch):
    calls = []
    def execute(command, **kwargs):
        calls.append(command)
        if command[1] == "run":
            raise subprocess.TimeoutExpired(command, 15)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess, "run", execute)
    assert grade_python("```python\ndef solve(xs): return xs\n```", [], [])["status"] == "timeout"
    assert calls[1] == ["docker", "rm", "--force", calls[0][3]]
