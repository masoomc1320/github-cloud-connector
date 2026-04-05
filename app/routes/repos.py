from __future__ import annotations

from datetime import datetime
from enum import Enum

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from ..config import load_settings, require_github_pat
from ..github_client import GitHubClient, GitHubClientError

router = APIRouter()


class OwnerKind(str, Enum):
    user = "user"
    org = "org"
    auto = "auto"


class Repository(BaseModel):
    name: str
    full_name: str
    private: bool
    html_url: str
    description: str | None = None
    language: str | None = None
    stargazers_count: int
    forks_count: int
    updated_at: datetime


class RepositoriesResponse(BaseModel):
    owner: str
    owner_kind: str
    repositories: list[Repository]


def _github_payload_message(payload: object | None) -> str | None:
    if isinstance(payload, dict):
        msg = payload.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg
    return None


def _map_github_error(err: GitHubClientError) -> HTTPException:
    status_code = err.status_code
    detail_msg = _github_payload_message(err.payload) or str(err)

    if status_code in (401, 403):
        # Token/auth problems between our service and GitHub.
        return HTTPException(status_code=502, detail=f"GitHub authentication/authorization failed: {detail_msg}")
    if status_code == 404:
        return HTTPException(status_code=404, detail=f"Owner not found: {detail_msg}")
    if status_code == 504:
        return HTTPException(status_code=504, detail="GitHub request timed out.")

    # Fallback for any other GitHub REST errors.
    if status_code is None:
        return HTTPException(status_code=502, detail=f"GitHub API error: {detail_msg}")
    return HTTPException(status_code=502, detail=f"GitHub API error ({status_code}): {detail_msg}")


@router.get(
    "/repos/{owner}",
    response_model=RepositoriesResponse,
    summary="Fetch repositories for a user or organization",
)
async def get_repos(
    owner: str = Path(..., min_length=1, description="GitHub username or organization name"),
    owner_kind: OwnerKind = Query(OwnerKind.auto, description="user, org, or auto"),
):
    settings = load_settings()

    try:
        token = require_github_pat(settings)
    except RuntimeError as e:
        # Required by assignment: return a clear error when `GITHUB_PAT` is missing.
        raise HTTPException(status_code=500, detail=str(e)) from e

    client = GitHubClient(
        token=token,
        api_base_url=settings.github_api_base_url,
        timeout_seconds=settings.github_timeout_seconds,
    )

    # Fetch repositories based on owner_kind.
    repos_raw: list[dict]
    used_kind: OwnerKind

    if owner_kind == OwnerKind.user:
        try:
            repos_raw = await client.get_user_repos(owner)
            used_kind = OwnerKind.user
        except GitHubClientError as e:
            raise _map_github_error(e) from e
    elif owner_kind == OwnerKind.org:
        try:
            repos_raw = await client.get_org_repos(owner)
            used_kind = OwnerKind.org
        except GitHubClientError as e:
            raise _map_github_error(e) from e
    else:
        # auto: try user first, then org on 404.
        try:
            repos_raw = await client.get_user_repos(owner)
            used_kind = OwnerKind.user
        except GitHubClientError as e_user:
            if e_user.status_code != 404:
                raise _map_github_error(e_user) from e_user

            try:
                repos_raw = await client.get_org_repos(owner)
                used_kind = OwnerKind.org
            except GitHubClientError as e_org:
                if e_org.status_code == 404:
                    raise HTTPException(status_code=404, detail="Owner not found.") from e_org
                raise _map_github_error(e_org) from e_org

    # Convert GitHub JSON objects into our API response model.
    try:
        repositories = [
            Repository(
                name=repo["name"],
                full_name=repo["full_name"],
                private=bool(repo["private"]),
                html_url=repo["html_url"],
                description=repo.get("description"),
                language=repo.get("language"),
                stargazers_count=int(repo["stargazers_count"]),
                forks_count=int(repo["forks_count"]),
                updated_at=repo["updated_at"],
            )
            for repo in repos_raw
        ]
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(
            status_code=502,
            detail="Unexpected GitHub repository payload format.",
        ) from e

    return RepositoriesResponse(owner=owner, owner_kind=used_kind.value, repositories=repositories)

