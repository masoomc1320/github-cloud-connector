import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    github_pat: str | None
    github_api_base_url: str
    github_timeout_seconds: float


def load_settings() -> Settings:
    github_pat = os.getenv("GITHUB_PAT")

    github_api_base_url = os.getenv("GITHUB_API_BASE_URL", "https://api.github.com")
    github_api_base_url = github_api_base_url.rstrip("/")

    timeout_raw = os.getenv("GITHUB_TIMEOUT_SECONDS", "15")
    try:
        github_timeout_seconds = float(timeout_raw)
    except ValueError as e:
        raise ValueError(f"Invalid `GITHUB_TIMEOUT_SECONDS`: {timeout_raw!r}") from e

    return Settings(
        github_pat=github_pat,
        github_api_base_url=github_api_base_url,
        github_timeout_seconds=github_timeout_seconds,
    )


def require_github_pat(settings: Settings) -> str:
    if not settings.github_pat:
        # The API layer can decide the HTTP status code.
        raise RuntimeError("Missing required environment variable `GITHUB_PAT`.")
    return settings.github_pat


