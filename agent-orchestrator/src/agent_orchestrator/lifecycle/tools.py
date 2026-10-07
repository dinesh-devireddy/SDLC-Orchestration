"""Bounded filesystem tools. Nothing in this module writes to the source repo."""

import ast
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import tempfile
import time

from .models import ChangeSet

SKIP = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".runs", "node_modules", "data"}
SUFFIXES = {".py", ".md", ".toml", ".ini", ".txt", ".json", ".yaml", ".yml"}
SECRET = re.compile(r"-----BEGIN .*PRIVATE KEY-----|sk-(?:proj-)?[A-Za-z0-9_-]{20,}")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def safe_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (not name or "\\" in name or path.is_absolute() or ":" in name
            or any(part in {".", ".."} or part.startswith(".") for part in name.split("/"))):
        raise ValueError("Unsafe file path")
    if path.suffix not in SUFFIXES or any(part in SKIP for part in path.parts):
        raise ValueError("File type or directory is outside the tool allowlist")
    if path.name in {"AGENTS.md", "conftest.py"}:
        # Read these as context, but do not let a proposal alter agent governance
        # or introduce pytest-wide hooks under this initial write policy.
        raise ValueError("Governance files and pytest hooks are read-only")
    return path


def read_snapshot(root: Path) -> dict[str, str]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Source must be a directory")
    result = {}
    size = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith(".")
                         and not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if name.startswith(".") or path.is_symlink() or path.suffix not in SUFFIXES:
                continue
            if path.stat().st_size > 50_000:
                raise ValueError("Snapshot file exceeds 50 KB; choose a smaller source directory")
            content = path.read_text(encoding="utf-8")
            if SECRET.search(content):
                raise ValueError("Potential credential found; remove it before creating a snapshot")
            size += len(content.encode())
            if size > 200_000 or len(result) >= 100:
                raise ValueError("Snapshot exceeds 100 files / 200 KB; choose a smaller source directory")
            result[path.relative_to(root).as_posix()] = content
    return result


def policy_check(proposal: dict, baseline: dict[str, str], task_ids: set[str]) -> dict:
    change_set = ChangeSet.model_validate(proposal)
    errors, high_impact = [], []
    if set(change_set.addressed_tasks) != task_ids:
        errors.append("Proposal must account for every task in the plan")
    for change in change_set.changes:
        try:
            path = safe_path(change.path)
        except ValueError as error:
            errors.append(str(error))
            continue
        if len(change.content.encode()) > 50_000 or SECRET.search(change.content):
            errors.append("File exceeds size limit or contains a potential credential")
        if any(part in {"migrations", "alembic"} for part in path.parts):
            high_impact.append("Database migration")
            if change.path in baseline:
                errors.append("Existing migrations cannot be modified")
        if path.name in {"pyproject.toml", "requirements.txt"}:
            high_impact.append("Dependency/configuration change")
        if path.suffix == ".py":
            high_impact.append("Executable code / possible API or security impact")
    return {"passed": not errors, "errors": errors, "high_impact": sorted(set(high_impact)),
            "approval_required": True}


def patch_text(baseline: dict[str, str], proposal: dict) -> str:
    lines = []
    for change in proposal["changes"]:
        for line in difflib.unified_diff(
            baseline.get(change["path"], "").splitlines(keepends=True),
            change["content"].splitlines(keepends=True),
            fromfile="a/" + change["path"] if change["path"] in baseline else "/dev/null",
            tofile="b/" + change["path"],
        ):
            lines.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
    return "".join(lines)


def restore_workspace(workspace: Path, baseline: dict[str, str]) -> None:
    # Only this run-owned directory can be restored. Source paths are never used.
    if workspace.name != "workspace" or workspace.is_symlink():
        raise ValueError("Invalid workspace")
    workspace.mkdir(parents=True, exist_ok=True)
    for directory, dirs, files in os.walk(workspace, topdown=False, followlinks=False):
        for name in files:
            (Path(directory) / name).unlink()
        for name in dirs:
            path = Path(directory) / name
            if path.is_symlink():
                path.unlink()
            else:
                path.rmdir()
    for name, content in baseline.items():
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def apply_proposal(workspace: Path, baseline: dict[str, str], proposal: dict) -> None:
    # Restore first: replay after a crash is idempotent, and repairs cannot retain
    # files from an older proposal. All paths were validated before approval.
    restore_workspace(workspace, baseline)
    for change in ChangeSet.model_validate(proposal).changes:
        path = workspace / safe_path(change.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(change.content, encoding="utf-8")


def static_scan(workspace: Path) -> dict:
    findings = []
    for path in workspace.rglob("*.py"):
        if path.is_symlink():
            findings.append("Symbolic link in workspace")
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                    findings.append(f"{path.relative_to(workspace)}: dynamic execution requires review")
        except (SyntaxError, UnicodeError):
            findings.append(f"{path.relative_to(workspace)}: invalid Python syntax")
    return {"passed": not findings, "findings": findings,
            "scope": "Python syntax and direct eval/exec calls only; not a security certification"}


def workspace_matches(workspace: Path, baseline: dict, proposal: dict) -> bool:
    expected = {**baseline, **{change["path"]: change["content"] for change in proposal["changes"]}}
    return read_snapshot(workspace) == expected


def run_tests(workspace: Path, stop_file: Path, timeout: float = 30, python: str = sys.executable) -> dict:
    # Human must explicitly authorize running repository code. shell=False and
    # a clean environment reduce risk, but this is NOT an OS security sandbox.
    command = [python, "-m", "pytest", "-q", "-o", "addopts=", "--confcutdir", str(workspace), "tests"]
    env = {"PATH": os.defpath, "PYTHONPATH": str(workspace / "src"),
           "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryFile() as output:
        env.update({"HOME": home, "TMPDIR": home, "TEMP": home, "TMP": home})
        process = subprocess.Popen(command, cwd=workspace, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=os.name != "nt")
        started = time.monotonic()
        reason = None
        while process.poll() is None:
            if stop_file.exists() or time.monotonic() - started > timeout or output.tell() > 1_000_000:
                reason = "stopped" if stop_file.exists() else "timeout_or_output_limit"
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                break
            time.sleep(0.05)
        process.wait()
        # Raw pytest output can contain secrets or private source. Keep it local;
        # only return bounded exit metadata to state, UI, and the LLM.
        return {"passed": process.returncode == 0 and reason is None,
                "exit_code": process.returncode, "reason": reason,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "command": "python -m pytest -q -o addopts= --confcutdir WORKSPACE tests",
                "output_redacted": True}
