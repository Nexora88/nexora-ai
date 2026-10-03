"""
Nexora AI — Test runner + self-heal desteği
Push öncesi pytest / npm test. Başarısızsa log döner (heal döngüsü dışarıda).
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class TestResult:
    ok: bool
    command: str
    exit_code: int
    stdout: str
    stderr: str
    framework: str = ""  # pytest | npm | none
    detail: str = ""


@dataclass
class WorkspaceResult:
    ok: bool
    test: TestResult
    work_dir: str = ""
    events: List[dict] = field(default_factory=list)


def detect_command(root: Path) -> tuple[str, str]:
    """(shell_command, framework)"""
    if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists():
        if shutil.which("pytest"):
            return "pytest -q --tb=short", "pytest"
    if (root / "package.json").exists():
        npm = shutil.which("npm")
        if npm:
            # test script yoksa npm test yine denenebilir
            return "npm test --silent", "npm"
    # Python projesi varsayımı
    if list(root.glob("**/test_*.py")) or list(root.glob("**/*_test.py")):
        if shutil.which("pytest"):
            return "pytest -q --tb=short", "pytest"
    return "", "none"


async def run_shell(command: str, cwd: str, timeout: float = 120.0) -> TestResult:
    if not command:
        return TestResult(
            ok=True,
            command="",
            exit_code=0,
            stdout="",
            stderr="",
            framework="none",
            detail="Test komutu yok — atlandı (yeşil sayılır)",
        )

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "CI": "1"},
        )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return TestResult(
                ok=False,
                command=command,
                exit_code=-1,
                stdout="",
                stderr="Timeout",
                detail=f"Test {timeout}s aşımı",
            )

        out = (out_b or b"").decode("utf-8", errors="replace")[-8000:]
        err = (err_b or b"").decode("utf-8", errors="replace")[-8000:]
        code = proc.returncode or 0
        return TestResult(
            ok=code == 0,
            command=command,
            exit_code=code,
            stdout=out,
            stderr=err,
            detail="passed" if code == 0 else "failed",
        )
    except Exception as e:
        return TestResult(
            ok=False,
            command=command,
            exit_code=-1,
            stdout="",
            stderr=str(e)[:500],
            detail="runner_error",
        )


def materialize_files(files: List[Dict[str, str]], base: Optional[Path] = None) -> Path:
    """
    files: [{path, content}]
    Geçici dizine yazar; path traversal engeli.
    """
    root = base or Path(tempfile.mkdtemp(prefix="nexora-ship-"))
    root = root.resolve()
    for f in files:
        rel = (f.get("path") or "").replace("\\", "/").lstrip("/")
        if not rel or ".." in rel.split("/"):
            continue
        target = (root / rel).resolve()
        if not str(target).startswith(str(root)):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.get("content") or "", encoding="utf-8")
    return root


async def run_tests_on_files(
    files: List[Dict[str, str]],
    extra_root_files: Optional[List[Dict[str, str]]] = None,
    timeout: float = 120.0,
) -> WorkspaceResult:
    """
    Sadece gelen dosyalarla izole workspace.
    Gerçek monorepo testleri için clone gerekir (sonraki sürüm).
    """
    events: List[dict] = []
    events.append({"agent": "qa", "step": "workspace", "status": "running", "detail": "Dosyalar yazılıyor"})

    all_files = list(files)
    if extra_root_files:
        all_files.extend(extra_root_files)

    root = materialize_files(all_files)
    events.append(
        {
            "agent": "qa",
            "step": "workspace",
            "status": "done",
            "detail": str(root),
        }
    )

    cmd, framework = detect_command(root)
    events.append(
        {
            "agent": "qa",
            "step": "detect",
            "status": "done",
            "detail": framework or "none",
        }
    )

    events.append(
        {
            "agent": "qa",
            "step": "test",
            "status": "running",
            "detail": cmd or "skip",
        }
    )
    result = await run_shell(cmd, str(root), timeout=timeout)
    result.framework = framework
    events.append(
        {
            "agent": "qa",
            "step": "test",
            "status": "done" if result.ok else "error",
            "detail": result.detail,
        }
    )

    return WorkspaceResult(ok=result.ok, test=result, work_dir=str(root), events=events)


def failure_blob(result: TestResult) -> str:
    """Heal için LLM'e verilecek hata özeti."""
    parts = [
        f"command: {result.command}",
        f"exit: {result.exit_code}",
        f"framework: {result.framework}",
        "--- stdout ---",
        result.stdout[-4000:],
        "--- stderr ---",
        result.stderr[-4000:],
    ]
    return "\n".join(parts)
