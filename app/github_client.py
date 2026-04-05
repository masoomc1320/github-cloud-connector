from __future__ import annotations

import httpx


class GitHubClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        payload: object | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class GitHubClient:
    def __init__(self, token: str, api_base_url: str, timeout_seconds: float):
        self._token = token
        self._api_base_url = api_base_url
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        # GitHub REST API accepts classic PATs using either `token` or `Bearer`.
        # We use `Bearer` to match the official docs.
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _request_json(self, method: str, path: str, *, params: dict | None = None) -> object:
        url_path = path if path.startswith("/") else f"/{path}"
        async with httpx.AsyncClient(
            base_url=self._api_base_url,
            timeout=self.timeout_seconds,
            headers=self._headers(),
        ) as client:
            try:
                resp = await client.request(method, url_path, params=params)
            except httpx.TimeoutException as e:
                raise GitHubClientError("GitHub request timed out.", status_code=504) from e
            except httpx.RequestError as e:
                raise GitHubClientError("Network error while contacting GitHub.", status_code=502) from e

        # Attempt to parse JSON error payload for debugging.
        payload: object | None = None
        try:
            payload = resp.json()
        except ValueError:
            payload = None

        if 200 <= resp.status_code < 300:
            try:
                return resp.json()
            except ValueError as e:
                raise GitHubClientError("GitHub returned a non-JSON response.", status_code=502, payload=payload) from e

        message = "GitHub API request failed."
        if isinstance(payload, dict):
            message = payload.get("message") or message

        raise GitHubClientError(
            message,
            status_code=resp.status_code,
            payload=payload,
        )

    async def get_user_repos(self, owner: str, *, per_page: int = 100) -> list[dict]:
        data = await self._request_json("GET", f"/users/{owner}/repos", params={"per_page": per_page})
        if not isinstance(data, list):
            raise GitHubClientError("Unexpected GitHub response format.", status_code=502, payload=data)
        return data  # type: ignore[return-value]

    async def get_org_repos(self, owner: str, *, per_page: int = 100) -> list[dict]:
        data = await self._request_json("GET", f"/orgs/{owner}/repos", params={"per_page": per_page})
        if not isinstance(data, list):
            raise GitHubClientError("Unexpected GitHub response format.", status_code=502, payload=data)
        return data  # type: ignore[return-value]

