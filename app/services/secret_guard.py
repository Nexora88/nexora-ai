"""
Nexora AI — Secret Guard
Commit/PR öncesi .env, API key, private key sızıntısını yakala.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


@dataclass
class SecretHit:
    path: str
    line: int
    kind: str
    snippet: str


PATTERNS = [
    ("env_file", re.compile(r"^\s*(SECRET|API|TOKEN|PASSWORD|PRIVATE)[A-Z0-9_]*\s*=\s*\S+", re.I | re.M)),
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("generic_key", re.compile(r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"]{8,}")),
    ("private_key", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("jwt_like", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("openai", re.compile(r"sk-[A-Za-z0-9]{20,}")),
]

BLOCK_PATHS = re.compile(r"(^|/)\.env(\.|$)|(^|/)credentials\.(json|yml)", re.I)


def scan_file(path: str, content: str) -> List[SecretHit]:
    hits: List[SecretHit] = []
    if BLOCK_PATHS.search(path.replace("\\", "/")):
        hits.append(SecretHit(path, 0, "blocked_path", path))
        return hits
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        for kind, pat in PATTERNS:
            if pat.search(line):
                snippet = line.strip()[:80]
                hits.append(SecretHit(path, i, kind, snippet))
                break
    return hits


def scan_files(files: list[dict]) -> List[SecretHit]:
    """files: [{path, content}, ...]"""
    all_hits: List[SecretHit] = []
    for f in files:
        all_hits.extend(scan_file(f.get("path") or "", f.get("content") or ""))
    return all_hits


def assert_clean(files: list[dict]) -> None:
    hits = scan_files(files)
    if hits:
        msg = "; ".join(f"{h.path}:{h.line} [{h.kind}]" for h in hits[:5])
        raise ValueError(f"Secret Guard engelledi: {msg}")
