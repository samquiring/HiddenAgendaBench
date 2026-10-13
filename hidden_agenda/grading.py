"""Execute candidate code only in a disposable container; compare results on host."""
import json
import re
import subprocess
import uuid


def grade_python(output, inputs, expected, image="python:3.12-slim"):
    blocks = re.findall(r"```python\s*\n(.*?)```", output, re.DOTALL)
    if len(blocks) != 1:
        return {"success": False, "status": "invalid_code_format"}
    runner = "import json,sys\np=json.load(sys.stdin)\nns={}\nexec(p['code'],ns)\nprint(json.dumps([ns['solve'](x) for x in p['inputs']]))\n"
    container_name = "hidden-agenda-" + uuid.uuid4().hex
    try:
        result = subprocess.run([
            "docker", "run", "--name", container_name, "--rm", "--pull=never", "--network=none", "--read-only",
            "--memory=128m", "--cpus=1", "--pids-limit=32", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--user=65534:65534", "-i", image,
            "python", "-I", "-c", runner,
        ], input=json.dumps({"code": blocks[0], "inputs": inputs}), text=True,
            capture_output=True, timeout=15)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "--force", container_name], capture_output=True, timeout=10)
        return {"success": False, "status": "timeout"}
    if result.returncode in (125, 126, 127):
        raise RuntimeError("Docker infrastructure failed: " + result.stderr[:1000])
    if result.returncode:
        return {"success": False, "status": "execution_error"}
    try:
        passed = json.loads(result.stdout) == expected
    except (ValueError, TypeError):
        passed = False
    return {"success": passed, "status": "graded"}


def grade_humaneval(output, problem, image="hidden-agenda-evalplus:0.3.1", timeout=180):
    """Use pinned EvalPlus oracles in a disposable, offline container."""
    blocks = re.findall(r"```python\s*\n(.*?)```", output, re.DOTALL)
    if len(blocks) != 1:
        return {"success": False, "status": "invalid_code_format"}
    name = "hidden-agenda-evalplus-" + uuid.uuid4().hex
    command = ["docker", "run", "--name", name, "--rm", "--pull=never",
               "--network=none", "--read-only", "--memory=1g", "--cpus=1",
               "--pids-limit=64", "--cap-drop=ALL", "--security-opt=no-new-privileges",
               "--user=65534:65534", "--tmpfs=/tmp:rw,noexec,nosuid,size=64m,mode=1777",
               "--env=EVALPLUS_MAX_MEMORY_BYTES=1073741824", "-i", image]
    try:
        result = subprocess.run(command, input=json.dumps(dict(problem=problem, solution=blocks[0])),
                                text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True, timeout=10)
        return {"success": False, "status": "timeout"}
    if result.returncode:
        # The trusted wrapper should return a failed grade for candidate errors.
        # Nonzero exit means infrastructure/oracle failure, not a coding failure.
        raise RuntimeError("EvalPlus infrastructure failed: " + result.stderr[-2000:])
    try:
        grade = json.loads(result.stdout)
    except ValueError as exc:
        raise RuntimeError("Invalid EvalPlus wrapper output") from exc
    if not isinstance(grade.get("success"), bool) or grade.get("status") != "graded":
        raise RuntimeError("Invalid EvalPlus grade schema")
    return grade
