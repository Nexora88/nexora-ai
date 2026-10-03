"""
Nexora AI — GitHub Ship
Seçili repoya branch + dosya commit + PR.
Kullanıcı arayüzde adımları görür; bu servis gerçek GitHub işini yapar.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings

GITHUB_API = "https://api.github.com"


@dataclass
class ShipFile:
    path: str
    content: str  # düz metin (utf-8)


@dataclass
class ShipStep:
    id: str
    label: str
    status: str  # pending | running | done | error
    detail: str = ""


@dataclass
class ShipResult:
    ok: bool
    steps: List[ShipStep] = field(default_factory=list)
    branch: str = ""
    commit_sha: str = ""
    pr_url: str = ""
    pr_number: Optional[int] = None
    error: str = ""
    html_url: str = ""


class GitHubShipError(Exception):
    def __init__(self, message: str, step_id: str = ""):
        super().__init__(message)
        self.step_id = step_id


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Nexora-AI-Ship",
    }


async def github_get(token: str, path: str, params: Optional[dict] = None) -> Any:
    async with httpx.AsyncClient(timeout=45.0) as client:
        r = await client.get(f"{GITHUB_API}{path}", headers=_headers(token), params=params)
        if r.status_code >= 400:
            raise GitHubShipError(f"GitHub GET {path}: {r.status_code} {r.text[:300]}")
        if r.status_code == 204 or not r.content:
            return None
        return r.json()


async def github_post(token: str, path: str, json_body: dict) -> Any:
    async with httpx.AsyncClient(timeout=45.0) as client:
        r = await client.post(f"{GITHUB_API}{path}", headers=_headers(token), json=json_body)
        if r.status_code >= 400:
            raise GitHubShipError(f"GitHub POST {path}: {r.status_code} {r.text[:300]}")
        return r.json()


async def github_put(token: str, path: str, json_body: dict) -> Any:
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.put(f"{GITHUB_API}{path}", headers=_headers(token), json=json_body)
        if r.status_code >= 400:
            raise GitHubShipError(f"GitHub PUT {path}: {r.status_code} {r.text[:300]}")
        return r.json()


async def list_user_repos(token: str, per_page: int = 50) -> List[dict]:
    data = await github_get(
        token,
        "/user/repos",
        params={"per_page": per_page, "sort": "updated", "affiliation": "owner,collaborator"},
    )
    out = []
    for repo in data or []:
        out.append(
            {
                "full_name": repo.get("full_name"),
                "private": repo.get("private"),
                "default_branch": repo.get("default_branch") or "main",
                "html_url": repo.get("html_url"),
            }
        )
    return out


async def get_authenticated_user(token: str) -> dict:
    return await github_get(token, "/user")


async def get_ref_sha(token: str, owner: str, repo: str, branch: str) -> str:
    data = await github_get(token, f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
    return data["object"]["sha"]


async def create_branch(
    token: str, owner: str, repo: str, new_branch: str, from_sha: str
) -> None:
    try:
        await github_post(
            token,
            f"/repos/{owner}/{repo}/git/refs",
            {"ref": f"refs/heads/{new_branch}", "sha": from_sha},
        )
    except GitHubShipError as e:
        # Branch already exists → continue (idempotent-ish)
        if "422" not in str(e):
            raise


async def put_file(
    token: str,
    owner: str,
    repo: str,
    branch: str,
    path: str,
    content: str,
    message: str,
) -> dict:
    """Tek dosya commit (Contents API)."""
    url_path = f"/repos/{owner}/{repo}/contents/{path.lstrip('/')}"
    # mevcut sha (update için)
    sha = None
    try:
        existing = await github_get(
            token, url_path, params={"ref": branch}
        )
        if isinstance(existing, dict):
            sha = existing.get("sha")
    except GitHubShipError:
        sha = None

    body: Dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha

    return await github_put(token, url_path, body)


async def create_pull_request(
    token: str,
    owner: str,
    repo: str,
    title: str,
    head: str,
    base: str,
    body: str,
) -> dict:
    return await github_post(
        token,
        f"/repos/{owner}/{repo}/pulls",
        {"title": title, "head": head, "base": base, "body": body},
    )


def parse_repo(full_name: str) -> tuple[str, str]:
    parts = (full_name or "").strip().split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise GitHubShipError("Repo formatı owner/name olmalı", "validate")
    return parts[0], parts[1]


async def run_ship(
    token: str,
    repo_full_name: str,
    files: List[ShipFile],
    commit_message: str,
    branch: str,
    create_pr: bool = True,
    pr_title: Optional[str] = None,
    pr_body: Optional[str] = None,
    base_branch: Optional[str] = None,
) -> ShipResult:
    """
    Adım adım ship. Frontend bu steps listesini canlı gösterebilir
    (endpoint her adımı stream etmeden tek seferde de dönebilir).
    """
    steps = [
        ShipStep("validate", "Görev doğrulanıyor", "pending"),
        ShipStep("repo", "Repo biliniyor", "pending"),
        ShipStep("branch", "Branch hazırlanıyor", "pending"),
        ShipStep("code", "Dosyalar yazılıyor", "pending"),
        ShipStep("commit", "Commit oluşturuluyor", "pending"),
        ShipStep("push", "GitHub'a iletiliyor", "pending"),
        ShipStep("pr", "Pull Request açılıyor", "pending"),
    ]

    def set_step(sid: str, status: str, detail: str = ""):
        for s in steps:
            if s.id == sid:
                s.status = status
                s.detail = detail
                break

    result = ShipResult(ok=False, steps=steps, branch=branch)

    try:
        if not token:
            raise GitHubShipError("GitHub bağlı değil", "validate")
        if not files:
            raise GitHubShipError("Yazılacak dosya yok", "validate")
        if not commit_message.strip():
            raise GitHubShipError("Commit mesajı boş", "validate")

        set_step("validate", "done", f"{len(files)} dosya")
        owner, repo = parse_repo(repo_full_name)
        set_step("repo", "running", repo_full_name)

        # default branch
        repo_info = await github_get(token, f"/repos/{owner}/{repo}")
        base = base_branch or repo_info.get("default_branch") or "main"
        set_step("repo", "done", f"base: {base}")

        set_step("branch", "running", branch)
        base_sha = await get_ref_sha(token, owner, repo, base)
        await create_branch(token, owner, repo, branch, base_sha)
        set_step("branch", "done", branch)

        set_step("code", "running", "")
        set_step("commit", "running", "")
        set_step("push", "running", "")

        last_commit = ""
        written = []
        for i, f in enumerate(files):
            msg = commit_message if i == 0 else f"{commit_message} ({f.path})"
            data = await put_file(
                token, owner, repo, branch, f.path, f.content, msg
            )
            last_commit = (data.get("commit") or {}).get("sha") or last_commit
            written.append(f.path)
            set_step("code", "running", f"yazıldı: {f.path}")

        set_step("code", "done", ", ".join(written[:5]))
        set_step("commit", "done", last_commit[:7] if last_commit else "ok")
        set_step("push", "done", f"branch/{branch}")
        result.commit_sha = last_commit
        result.branch = branch
        result.html_url = f"https://github.com/{owner}/{repo}/tree/{branch}"

        if create_pr:
            set_step("pr", "running", "")
            pr = await create_pull_request(
                token,
                owner,
                repo,
                title=pr_title or commit_message[:72],
                head=branch,
                base=base,
                body=pr_body
                or (
                    "## Nexora Ship\n\n"
                    "Bu PR Nexora AI tarafından oluşturuldu.\n\n"
                    f"**Commit:** {commit_message}\n\n"
                    "Data · Intelligence · Future"
                ),
            )
            result.pr_url = pr.get("html_url") or ""
            result.pr_number = pr.get("number")
            set_step("pr", "done", result.pr_url)
        else:
            set_step("pr", "done", "PR atlandı")

        result.ok = True
        return result

    except GitHubShipError as e:
        if e.step_id:
            set_step(e.step_id, "error", str(e))
        else:
            # son running adımı error yap
            for s in reversed(steps):
                if s.status in ("running", "pending"):
                    s.status = "error"
                    s.detail = str(e)
                    break
        result.error = str(e)
        return result
    except Exception as e:
        for s in reversed(steps):
            if s.status in ("running", "pending"):
                s.status = "error"
                s.detail = str(e)[:200]
                break
        result.error = str(e)[:300]
        return result


def steps_as_dict(result: ShipResult) -> List[dict]:
    return [
        {"id": s.id, "label": s.label, "status": s.status, "detail": s.detail}
        for s in result.steps
                                                                        ]
