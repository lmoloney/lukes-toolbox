"""Configuration loading for the Fabric SQL public-client CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SQL_SCOPE = "https://database.windows.net/.default"
IDENTITY_DIAGNOSTIC_SQL = (
    "SELECT SUSER_SNAME() AS [suser_sname], "
    "USER_NAME() AS [user_name], "
    "CURRENT_USER AS [current_user]"
)
VALID_FLOWS = {"interactive", "device-code", "password"}


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    tenant_id: str
    public_client_id: str
    sql_endpoint: str
    database_name: str
    default_flow: str
    cache_path: Path
    sql_login_timeout_seconds: int
    login_hint: str | None
    public_client_username: str | None
    public_client_password: str | None
    default_query: str | None

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @property
    def scopes(self) -> list[str]:
        return [DEFAULT_SQL_SCOPE]


def load_config(env_file: Path | None = None) -> AppConfig:
    env_path = env_file or BASE_DIR / ".env"
    load_dotenv(env_path)

    default_flow = _optional("DEFAULT_FLOW") or "interactive"
    if default_flow not in VALID_FLOWS:
        raise ConfigError(
            f"DEFAULT_FLOW must be one of {', '.join(sorted(VALID_FLOWS))}; got {default_flow!r}"
        )

    cache_path = _cache_path(_optional("MSAL_CACHE_PATH") or ".msal_token_cache.json")

    return AppConfig(
        tenant_id=_required("TENANT_ID"),
        public_client_id=_required("PUBLIC_CLIENT_ID"),
        sql_endpoint=_normalize_sql_endpoint(_required("SQL_ENDPOINT")),
        database_name=_required("DATABASE_NAME"),
        default_flow=default_flow,
        cache_path=cache_path,
        sql_login_timeout_seconds=_positive_int("SQL_LOGIN_TIMEOUT_SECONDS", default=30),
        login_hint=_optional("LOGIN_HINT"),
        public_client_username=_optional("PUBLIC_CLIENT_USERNAME"),
        public_client_password=_optional("PUBLIC_CLIENT_PASSWORD"),
        default_query=_optional("DEFAULT_QUERY"),
    )


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value or value.startswith("<"):
        raise ConfigError(
            f"Missing or placeholder env var {name}. Copy .env.example to .env and fill it in."
        )
    return value


def _optional(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if not value or value.startswith("<"):
        return None
    return value


def _positive_int(name: str, default: int) -> int:
    value = _optional(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer; got {value!r}") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be greater than zero; got {parsed}")
    return parsed


def _cache_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def _normalize_sql_endpoint(value: str) -> str:
    endpoint = value.strip().rstrip(";")
    if endpoint.lower().startswith("tcp:"):
        endpoint = endpoint[4:]
    if endpoint.endswith(",1433"):
        endpoint = endpoint[:-5]
    if endpoint.endswith(":1433"):
        endpoint = endpoint[:-5]
    return endpoint
