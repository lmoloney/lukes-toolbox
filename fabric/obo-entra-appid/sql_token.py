"""Fabric SQL connection helpers for Entra access-token authentication."""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass
from typing import Any

SQL_COPT_SS_ACCESS_TOKEN = 1256


class SqlDependencyError(RuntimeError):
    """Raised when the SQL driver dependency is unavailable."""


class SqlConnectionError(RuntimeError):
    """Raised when SQL connection setup fails."""


class SqlExecutionError(RuntimeError):
    """Raised when SQL execution fails."""


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    rowcount: int


def access_token_struct(access_token: str) -> bytes:
    token_bytes = access_token.encode("UTF-16-LE")
    return struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)


def connect_with_access_token(
    server: str,
    database: str,
    access_token: str,
    pool_tag: str,
    timeout_seconds: int,
):
    try:
        import mssql_python
    except ImportError as exc:
        raise SqlDependencyError(
            "mssql-python could not be imported. Use Python 3.12 for this tool and install "
            f"dependencies with .venv/bin/python -m pip install -r requirements.txt "
            f"(current Python: {sys.version.split()[0]})."
        ) from exc

    packet_size = 4096 if sum(ord(char) for char in pool_tag) % 2 == 0 else 8192
    conn_str = (
        f"Server={server},1433;"
        f"Database={database};"
        "Encrypt=yes;"
        f"PacketSize={packet_size};"
    )
    token_struct = access_token_struct(access_token)

    try:
        return mssql_python.connect(
            conn_str,
            attrs_before={
                SQL_COPT_SS_ACCESS_TOKEN: token_struct,
                mssql_python.SQL_ATTR_LOGIN_TIMEOUT: timeout_seconds,
            },
        )
    except Exception as exc:
        message = str(exc)
        if "TCP Provider: Error code 0x102" in message:
            message = (
                f"{message}. TCP 1433 to the Fabric SQL endpoint timed out; "
                "check VPN, firewall, network allowlists, and Fabric/SQL service tag access."
            )
        raise SqlConnectionError(f"SQL connection failed: {message}") from exc


def execute_sql(conn, sql: str) -> QueryResult:
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        rowcount = cursor.rowcount
        if cursor.description:
            columns = [description[0] for description in cursor.description]
            rows = [tuple(row) for row in cursor.fetchall()]
        else:
            columns = []
            rows = []
        return QueryResult(columns=columns, rows=rows, rowcount=rowcount)
    except Exception as exc:
        raise SqlExecutionError(f"SQL execution failed: {exc}") from exc
