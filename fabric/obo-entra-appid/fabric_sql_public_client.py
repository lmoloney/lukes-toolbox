#!/usr/bin/env python3
"""CLI for Fabric SQL access through a dedicated Entra public client app."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import msal

from claims import decode_unverified_claims, selected_claims
from config import (
    BASE_DIR,
    IDENTITY_DIAGNOSTIC_SQL,
    AppConfig,
    ConfigError,
    VALID_FLOWS,
    load_config,
)
from sql_token import (
    QueryResult,
    SqlConnectionError,
    SqlDependencyError,
    SqlExecutionError,
    connect_with_access_token,
    execute_sql,
)


class AuthError(RuntimeError):
    """Raised when token acquisition fails."""


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "cache-clear":
            clear_cache(cache_path_from_env(args.env_file))
            return 0

        cfg = load_config(args.env_file)
        flow = args.flow or cfg.default_flow
        login_hint = args.login_hint or cfg.login_hint
        if flow == "password" and not login_hint:
            login_hint = cfg.public_client_username
        token = acquire_sql_token(
            cfg,
            flow=flow,
            no_cache=args.no_cache,
            login_hint=login_hint,
        )

        if args.command == "diagnose":
            run_diagnose(cfg, token, args.sql)
            return 0
        if args.command == "query":
            run_query(cfg, token, args.sql)
            return 0

        parser.error("No command provided")
        return 2
    except (ConfigError, AuthError, SqlDependencyError, SqlConnectionError, SqlExecutionError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Connect to Fabric SQL using a dedicated Entra public client app."
    )
    add_common_args(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    diagnose = subparsers.add_parser(
        "diagnose",
        parents=[common_arg_parser()],
        help="Acquire a SQL token, print safe claims, and run SQL identity diagnostics.",
    )
    diagnose.add_argument(
        "--sql",
        default=None,
        help="Optional extra SQL query to run after identity diagnostics.",
    )

    query = subparsers.add_parser(
        "query",
        parents=[common_arg_parser()],
        help="Run caller-supplied SQL.",
    )
    query.add_argument("--sql", required=True, help="SQL statement to execute.")

    subparsers.add_parser(
        "cache-clear",
        parents=[common_arg_parser()],
        help="Delete the local MSAL token cache file.",
    )
    return parser


def common_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    add_common_args(parser, suppress_defaults=True)
    return parser


def add_common_args(parser: argparse.ArgumentParser, suppress_defaults: bool = False) -> None:
    default = argparse.SUPPRESS if suppress_defaults else None
    no_cache_default = argparse.SUPPRESS if suppress_defaults else False
    parser.add_argument(
        "--env-file",
        type=Path,
        default=default,
        help="Path to .env file (default: .env next to this script).",
    )
    parser.add_argument(
        "--flow",
        choices=sorted(VALID_FLOWS),
        default=default,
        help="Auth flow to use (default: DEFAULT_FLOW from .env, usually interactive).",
    )
    parser.add_argument(
        "--login-hint",
        default=default,
        help="Optional login hint for interactive browser auth.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=no_cache_default,
        help="Do not read or write the persistent MSAL token cache.",
    )


def acquire_sql_token(
    cfg: AppConfig,
    flow: str,
    no_cache: bool,
    login_hint: str | None,
) -> str:
    if flow not in VALID_FLOWS:
        raise AuthError(f"Unsupported auth flow {flow!r}")

    cache = None if no_cache else load_token_cache(cfg.cache_path)
    app = msal.PublicClientApplication(
        client_id=cfg.public_client_id,
        authority=cfg.authority,
        token_cache=cache,
    )

    result: dict[str, Any] | None = None
    if cache is not None:
        accounts = app.get_accounts(username=login_hint) if login_hint else app.get_accounts()
        if not login_hint and len(accounts) > 1:
            raise AuthError(
                "Multiple accounts found in the token cache. Set LOGIN_HINT/--login-hint, "
                "use --no-cache, or run cache-clear before continuing."
            )
        for account in accounts:
            result = app.acquire_token_silent(cfg.scopes, account=account)
            if result and "access_token" in result:
                print("Using cached SQL token.")
                break

    if not result or "access_token" not in result:
        if flow == "interactive":
            kwargs: dict[str, Any] = {"scopes": cfg.scopes}
            if login_hint:
                kwargs["login_hint"] = login_hint
            result = app.acquire_token_interactive(**kwargs)
        elif flow == "device-code":
            device_flow = app.initiate_device_flow(scopes=cfg.scopes)
            if "user_code" not in device_flow:
                raise AuthError(f"Failed to create device-code flow: {device_flow}")
            print(device_flow["message"], flush=True)
            result = app.acquire_token_by_device_flow(device_flow)
        else:
            if not cfg.public_client_username or not cfg.public_client_password:
                raise AuthError(
                    "Password flow requires PUBLIC_CLIENT_USERNAME and PUBLIC_CLIENT_PASSWORD."
                )
            if login_hint and login_hint.casefold() != cfg.public_client_username.casefold():
                raise AuthError("LOGIN_HINT must match PUBLIC_CLIENT_USERNAME for password flow.")
            result = app.acquire_token_by_username_password(
                username=cfg.public_client_username,
                password=cfg.public_client_password,
                scopes=cfg.scopes,
            )

    if "access_token" not in result:
        error = result.get("error", "unknown_error")
        description = result.get("error_description", "No error description returned.")
        raise AuthError(f"Token acquisition failed: {error}: {description}")

    access_token = result["access_token"]
    if login_hint:
        validate_login_hint(access_token, login_hint)

    if cache is not None and cache.has_state_changed:
        save_token_cache(cfg.cache_path, cache)

    return access_token


def load_token_cache(path: Path) -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if path.exists():
        secure_cache_file(path)
        cache.deserialize(path.read_text(encoding="utf-8"))
    return cache


def save_token_cache(path: Path, cache: msal.SerializableTokenCache) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as cache_file:
            fd = -1
            cache_file.write(cache.serialize())
    except OSError as exc:
        if fd != -1:
            os.close(fd)
        raise AuthError(f"Could not secure token cache permissions on {path}") from exc


def secure_cache_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        raise AuthError(f"Could not secure token cache permissions on {path}") from exc


def clear_cache(path: Path) -> None:
    if path.exists():
        path.unlink()
        print(f"Deleted token cache: {path}")
    else:
        print(f"No token cache found at: {path}")


def cache_path_from_env(env_file: Path | None) -> Path:
    try:
        return load_config(env_file).cache_path
    except ConfigError:
        return BASE_DIR / ".msal_token_cache.json"


def validate_login_hint(access_token: str, login_hint: str) -> None:
    claims = decode_unverified_claims(access_token)
    candidates = [
        claims.get("preferred_username"),
        claims.get("upn"),
        claims.get("unique_name"),
    ]
    normalized_hint = login_hint.casefold()
    normalized_candidates = {
        str(candidate).casefold()
        for candidate in candidates
        if isinstance(candidate, str) and candidate
    }
    if normalized_hint not in normalized_candidates:
        shown_candidates = ", ".join(sorted(normalized_candidates)) or "no user claim"
        raise AuthError(
            f"Token user claim did not match login hint {login_hint!r}; got {shown_candidates}."
        )


def run_diagnose(cfg: AppConfig, access_token: str, extra_sql: str | None) -> None:
    print_section("Token claims (unverified diagnostics)")
    claims = selected_claims(decode_unverified_claims(access_token))
    print(json.dumps(claims, indent=2, sort_keys=True))
    print(
        "\nApp-client evidence is in claims such as appid/azp. "
        "SQL identity below should show the delegated UPN/user context."
    )

    print_section("SQL identity")
    run_query(cfg, access_token, IDENTITY_DIAGNOSTIC_SQL)

    configured_sql = cfg.default_query
    if extra_sql:
        print_section("Extra query")
        run_query(cfg, access_token, extra_sql)
    elif configured_sql:
        print_section("Configured default query")
        run_query(cfg, access_token, configured_sql)


def run_query(cfg: AppConfig, access_token: str, sql: str) -> None:
    conn = connect_with_access_token(
        cfg.sql_endpoint,
        cfg.database_name,
        access_token,
        pool_tag=cfg.public_client_id,
        timeout_seconds=cfg.sql_login_timeout_seconds,
    )
    try:
        result = execute_sql(conn, sql)
        try:
            conn.commit()
        except Exception as exc:
            raise SqlExecutionError(f"SQL commit failed: {exc}") from exc
    finally:
        conn.close()
    print_query_result(result)


def print_query_result(result: QueryResult) -> None:
    if not result.columns:
        print(f"Statement executed. Row count: {result.rowcount}")
        return

    rows = [[stringify(value) for value in row] for row in result.rows]
    widths = [
        max(len(column), *(len(row[index]) for row in rows)) if rows else len(column)
        for index, column in enumerate(result.columns)
    ]

    header = " | ".join(column.ljust(widths[index]) for index, column in enumerate(result.columns))
    divider = "-+-".join("-" * width for width in widths)
    print(header)
    print(divider)
    for row in rows:
        print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
    print(f"\n{len(rows)} row(s)")


def stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def print_section(title: str) -> None:
    print(f"\n{'=' * len(title)}")
    print(title)
    print(f"{'=' * len(title)}")


if __name__ == "__main__":
    raise SystemExit(main())
