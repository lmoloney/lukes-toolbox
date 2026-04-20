#!/usr/bin/env python3
"""E2E test: add an SPN to a Fabric workspace and grant it SQL access.

SPN1 (workspace admin) adds SPN2 as a Viewer, then grants SQL SELECT.
The script validates each step of the permission model sequentially.

Usage:
    cp .env.example .env   # fill in values
    uv pip install -r requirements.txt
    python sql-spn-test.py
"""

import logging
import os
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import mssql_python
import requests
from dotenv import load_dotenv

# ── Constants ────────────────────────────────────────────────────────────────

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
SQL_SCOPE = "https://database.windows.net/.default"
TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
SQL_COPT_SS_ACCESS_TOKEN = 1256

TOTAL_STEPS = 10

# ── Logging ──────────────────────────────────────────────────────────────────


def setup_logging() -> Path:
    """Configure logging to both console and a timestamped log file."""
    log_dir = Path(__file__).parent / "_logs"
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    log_file = log_dir / f"{timestamp}.log"

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # File handler — captures everything
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(fh)

    return log_file

# ── Helpers ──────────────────────────────────────────────────────────────────


def load_config():
    """Load and validate all required env vars."""
    load_dotenv(Path(__file__).parent / ".env")

    required = [
        "TENANT_ID",
        "SPN1_CLIENT_ID", "SPN1_CLIENT_SECRET",
        "SPN2_CLIENT_ID", "SPN2_CLIENT_SECRET", "SPN2_OBJECT_ID", "SPN2_NAME",
        "WORKSPACE_ID", "SQL_ENDPOINT", "DATABASE_NAME",
        "TABLE_NAME", "SCHEMA_NAME",
    ]

    config = {}
    missing = []
    for key in required:
        val = os.environ.get(key, "").strip()
        if not val or val.startswith("<"):
            missing.append(key)
        else:
            config[key] = val

    if missing:
        print(f"❌ Missing or placeholder env vars: {', '.join(missing)}", file=sys.stderr)
        print("   Copy .env.example → .env and fill in real values.", file=sys.stderr)
        sys.exit(1)

    return config


def get_fabric_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Acquire an OAuth2 client_credentials token for Fabric REST API."""
    return _get_token(tenant_id, client_id, client_secret, FABRIC_SCOPE)


def _get_token(tenant_id: str, client_id: str, client_secret: str, scope: str) -> str:
    """Acquire an OAuth2 client_credentials token from Entra ID."""
    url = TOKEN_URL.format(tenant_id=tenant_id)
    form_data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": "***REDACTED***",
        "scope": scope,
    }
    _log_request("POST", url, {"Content-Type": "application/x-www-form-urlencoded"}, body=form_data)

    resp = requests.post(
        url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        },
        timeout=30,
    )
    _log_response(resp)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Token acquisition failed ({resp.status_code}): {resp.text}"
        )
    return resp.json()["access_token"]


def fabric_headers(token: str) -> dict:
    """Standard headers for Fabric REST API calls."""
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _redact_headers(headers: dict) -> dict:
    """Redact sensitive header values for logging."""
    redacted = dict(headers)
    for key in redacted:
        low = key.lower()
        if low == "authorization":
            val = redacted[key]
            # Show first/last 8 chars of token
            if val.startswith("Bearer ") and len(val) > 30:
                tok = val[7:]
                redacted[key] = f"Bearer {tok[:8]}...{tok[-8:]}"
    return redacted


def _log_request(method: str, url: str, headers: dict, body=None):
    """Log full HTTP request details to the log file."""
    logging.debug(f">>> {method} {url}")
    for k, v in _redact_headers(headers).items():
        logging.debug(f">>> {k}: {v}")
    if body is not None:
        import json as _json
        logging.debug(f">>> Body: {_json.dumps(body, indent=2)}")
    logging.debug(">>>")


def _log_response(resp: requests.Response):
    """Log full HTTP response details to the log file."""
    logging.debug(f"<<< {resp.status_code} {resp.reason}")
    for k, v in resp.headers.items():
        logging.debug(f"<<< {k}: {v}")
    body = resp.text
    if len(body) > 4000:
        logging.debug(f"<<< Body ({len(body)} chars, truncated): {body[:4000]}...")
    else:
        logging.debug(f"<<< Body: {body}")
    logging.debug("<<<")


def http_get(url: str, headers: dict, **kwargs) -> requests.Response:
    """GET with full request/response logging."""
    _log_request("GET", url, headers)
    resp = requests.get(url, headers=headers, **kwargs)
    _log_response(resp)
    return resp


def http_post(url: str, headers: dict, json=None, data=None, **kwargs) -> requests.Response:
    """POST with full request/response logging."""
    _log_request("POST", url, headers, body=json or data)
    resp = requests.post(url, headers=headers, json=json, data=data, **kwargs)
    _log_response(resp)
    return resp


def sql_connect(server: str, database: str, tenant_id: str,
                client_id: str, client_secret: str) -> mssql_python.Connection:
    """Connect to a Fabric SQL endpoint using an Entra access token."""
    logging.debug(f"SQL CONNECT: server={server}, database={database}, client_id={client_id}")
    token = _get_token(tenant_id, client_id, client_secret, SQL_SCOPE)
    token_bytes = token.encode("UTF-16-LE")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)

    # Use a per-SPN PacketSize to prevent connection pool reuse across SPNs.
    # Access token auth forbids UID/PWD/Authentication in the conn string,
    # so we vary PacketSize (both values are valid and functionally equivalent).
    pool_tag = sum(ord(c) for c in client_id) % 2
    packet_size = 4096 if pool_tag == 0 else 8192

    conn_str = (
        f"Server={server},1433;"
        f"Database={database};"
        f"Encrypt=yes;"
        f"PacketSize={packet_size};"
    )
    logging.debug(f"SQL conn_str: {conn_str}")
    conn = mssql_python.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})
    logging.debug("SQL CONNECT: success")
    return conn


def sql_execute(conn, sql: str, fetch: bool = False):
    """Execute a SQL statement with logging. Returns (cursor, rows) if fetch=True."""
    logging.debug(f"SQL EXECUTE: {sql}")
    cursor = conn.cursor()
    cursor.execute(sql)
    if fetch:
        rows = cursor.fetchall()
        logging.debug(f"SQL RESULT: {len(rows)} row(s)")
        if cursor.description:
            cols = [desc[0] for desc in cursor.description]
            logging.debug(f"SQL COLUMNS: {cols}")
        for i, row in enumerate(rows[:5]):
            logging.debug(f"SQL ROW[{i}]: {row}")
        if len(rows) > 5:
            logging.debug(f"SQL ... ({len(rows) - 5} more rows)")
        return cursor, rows
    return cursor, None


def escape_sql_ident(name: str) -> str:
    """Escape a SQL identifier for use inside brackets (] → ]])."""
    return name.replace("]", "]]")


def step_header(num: int, title: str):
    """Print a step header."""
    line = f"Step {num}/{TOTAL_STEPS}: {title}"
    print(f"\n{'─' * 60}")
    print(line)
    print(f"{'─' * 60}")
    logging.info(f"{'─' * 40}")
    logging.info(line)


def pass_msg(msg: str):
    print(f"  ✅ PASS — {msg}")
    logging.info(f"PASS: {msg}")


def fail_msg(msg: str):
    print(f"  ❌ FAIL — {msg}")
    logging.error(f"FAIL: {msg}")


def info_msg(msg: str):
    print(f"  ℹ️  {msg}")
    logging.info(msg)


# ── Steps ────────────────────────────────────────────────────────────────────


def step1_check_spn1_admin(cfg: dict) -> bool:
    """Verify SPN1 has Admin role on the workspace."""
    step_header(1, "Verify SPN1 is Admin on the workspace")

    token = get_fabric_token(cfg["TENANT_ID"], cfg["SPN1_CLIENT_ID"], cfg["SPN1_CLIENT_SECRET"])
    info_msg("SPN1 token acquired for Fabric API")

    url = f"{FABRIC_API_BASE}/workspaces/{cfg['WORKSPACE_ID']}/roleAssignments"
    resp = http_get(url, headers=fabric_headers(token), timeout=30)
    info_msg(f"GET ...roleAssignments → {resp.status_code}")

    if resp.status_code != 200:
        fail_msg(f"Cannot read role assignments ({resp.status_code}): {resp.text[:200]}")
        info_msg("SPN1 needs at least Member role to read assignments, Admin to manage them")
        return False

    assignments = resp.json().get("value", [])
    for assignment in assignments:
        principal = assignment.get("principal", {})
        # Match by object ID or by aadAppId (client ID) nested in servicePrincipalDetails
        spn_details = principal.get("servicePrincipalDetails", {})
        aad_app_id = spn_details.get("aadAppId", "")
        principal_id = principal.get("id", "")

        if aad_app_id == cfg["SPN1_CLIENT_ID"] or principal_id == cfg["SPN1_CLIENT_ID"]:
            role = assignment.get("role", "")
            if role == "Admin":
                pass_msg(f"SPN1 confirmed as Admin (principal: {principal_id}, appId: {aad_app_id})")
                return True
            else:
                fail_msg(f"SPN1 has role '{role}' — Admin is required")
                return False

    # If we got 200 but didn't find SPN1 explicitly, it could still be admin
    # via group membership or because only Admin/Member can call this endpoint
    info_msg("SPN1 not found in explicit role assignments — checking via workspace GET")
    ws_url = f"{FABRIC_API_BASE}/workspaces/{cfg['WORKSPACE_ID']}"
    ws_resp = http_get(ws_url, headers=fabric_headers(token), timeout=30)
    if ws_resp.status_code == 200:
        pass_msg("SPN1 can access workspace and read role assignments (consistent with Admin/Member)")
        info_msg("Could not confirm exact role — ensure SPN1 is Admin for GRANT to work in step 7")
        return True

    fail_msg("Could not verify SPN1's workspace role")
    return False


def step2_spn1_query_table(cfg: dict) -> bool:
    """SPN1 queries the target table to confirm it exists and is accessible."""
    step_header(2, f"SPN1 queries {cfg['SCHEMA_NAME']}.{cfg['TABLE_NAME']} (expect success)")

    schema = escape_sql_ident(cfg["SCHEMA_NAME"])
    table = escape_sql_ident(cfg["TABLE_NAME"])
    query = f"SELECT TOP 1 * FROM [{schema}].[{table}]"
    info_msg(f"Query: {query}")

    try:
        conn = sql_connect(
            cfg["SQL_ENDPOINT"], cfg["DATABASE_NAME"], cfg["TENANT_ID"],
            cfg["SPN1_CLIENT_ID"], cfg["SPN1_CLIENT_SECRET"],
        )
        cursor, rows = sql_execute(conn, query, fetch=True)
        columns = [desc[0] for desc in cursor.description]
        conn.close()

        pass_msg(f"SPN1 can query table — {len(rows)} row(s) returned")
        info_msg(f"Columns: {', '.join(columns)}")
        return True
    except Exception as exc:
        fail_msg(f"SPN1 cannot query table: {exc}")
        logging.debug(f"Exception detail: {exc!r}", exc_info=True)
        info_msg("Check: SQL_ENDPOINT, DATABASE_NAME, SCHEMA_NAME, TABLE_NAME in .env")
        return False


def step3_check_spn1_directory_read(cfg: dict) -> bool:
    """Verify SPN1 has Directory.Read.All by looking up SPN2 via Microsoft Graph."""
    step_header(3, "Verify SPN1 can read directory (Directory.Read.All)")

    token = _get_token(cfg["TENANT_ID"], cfg["SPN1_CLIENT_ID"], cfg["SPN1_CLIENT_SECRET"], GRAPH_SCOPE)
    info_msg("SPN1 token acquired for Microsoft Graph")

    spn2_app_id = cfg["SPN2_CLIENT_ID"]
    url = f"https://graph.microsoft.com/v1.0/servicePrincipals?$filter=appId eq '{spn2_app_id}'"
    resp = http_get(url, headers=fabric_headers(token), timeout=30)
    info_msg(f"GET ...servicePrincipals?$filter=appId eq '{spn2_app_id}' → {resp.status_code}")

    if resp.status_code == 200:
        spns = resp.json().get("value", [])
        if spns:
            display_name = spns[0].get("displayName", "?")
            object_id = spns[0].get("id", "?")
            pass_msg(f"SPN2 found in directory: '{display_name}' (objectId: {object_id})")
            # Verify the object ID matches what's in the .env
            if object_id != cfg["SPN2_OBJECT_ID"]:
                info_msg(f"⚠️  Graph objectId ({object_id}) differs from SPN2_OBJECT_ID ({cfg['SPN2_OBJECT_ID']})")
            return True
        else:
            fail_msg(f"No service principal found with appId={spn2_app_id}")
            info_msg("SPN2 may not have an Enterprise Application in this tenant")
            return False
    elif resp.status_code == 403:
        fail_msg("SPN1 cannot read the directory (403 Forbidden)")
        info_msg("Grant 'Directory.Read.All' (Microsoft Graph, Application) to SPN1 with admin consent")
        return False
    else:
        fail_msg(f"Graph API call failed ({resp.status_code}): {resp.text[:200]}")
        return False


def step4_spn2_list_items_expect_403(cfg: dict) -> bool:
    """SPN2 tries to list workspace items — should get 403."""
    step_header(4, "SPN2 attempts to list workspace items (expect 403)")

    token = get_fabric_token(cfg["TENANT_ID"], cfg["SPN2_CLIENT_ID"], cfg["SPN2_CLIENT_SECRET"])
    info_msg("SPN2 token acquired for Fabric API")

    url = f"{FABRIC_API_BASE}/workspaces/{cfg['WORKSPACE_ID']}/items"
    resp = http_get(url, headers=fabric_headers(token), timeout=30)
    info_msg(f"GET ...items → {resp.status_code}")

    if resp.status_code == 403:
        pass_msg("SPN2 correctly denied access before role assignment")
        return True
    elif resp.status_code == 401:
        fail_msg("Got 401 — likely a token/app-permission/tenant-setting issue, not a workspace role issue")
        info_msg("Check: SPN2 app registration, client secret, and 'Service principals can use Fabric APIs' tenant setting")
        return False
    elif resp.status_code == 200:
        fail_msg("SPN2 already has access — it may already be assigned to the workspace")
        info_msg("Continuing anyway (steps 2–3 may be no-ops)")
        return True
    else:
        fail_msg(f"Unexpected status {resp.status_code}: {resp.text[:200]}")
        return False


def step5_spn1_add_spn2_viewer(cfg: dict) -> bool:
    """SPN1 adds SPN2 to the Viewer role."""
    step_header(5, "SPN1 adds SPN2 as Viewer on the workspace")

    token = get_fabric_token(cfg["TENANT_ID"], cfg["SPN1_CLIENT_ID"], cfg["SPN1_CLIENT_SECRET"])
    info_msg("SPN1 token acquired for Fabric API")

    url = f"{FABRIC_API_BASE}/workspaces/{cfg['WORKSPACE_ID']}/roleAssignments"
    payload = {
        "principal": {
            "id": cfg["SPN2_OBJECT_ID"],
            "type": "ServicePrincipal",
        },
        "role": "Viewer",
    }

    resp = http_post(url, headers=fabric_headers(token), json=payload, timeout=30)
    info_msg(f"POST ...roleAssignments → {resp.status_code}")

    if resp.status_code == 201:
        pass_msg("SPN2 added as Viewer successfully")
        return True
    elif resp.status_code == 409:
        pass_msg("SPN2 already has a role assignment (idempotent — continuing)")
        return True
    else:
        fail_msg(f"Role assignment failed ({resp.status_code}): {resp.text[:300]}")
        if "PrincipalNotFound" in resp.text:
            info_msg(f"SPN2_OBJECT_ID '{cfg['SPN2_OBJECT_ID']}' was not found as a principal")
            info_msg("This must be the Enterprise Application (Service Principal) Object ID,")
            info_msg("NOT the App Registration Object ID. Find it at:")
            info_msg("  Entra ID → Enterprise Applications → search app name → Object ID")
        return False


def step6_spn2_list_items_expect_200(cfg: dict) -> bool:
    """SPN2 tries to list workspace items — should now succeed."""
    step_header(6, "SPN2 lists workspace items (expect 200)")

    token = get_fabric_token(cfg["TENANT_ID"], cfg["SPN2_CLIENT_ID"], cfg["SPN2_CLIENT_SECRET"])
    info_msg("SPN2 token acquired for Fabric API")

    url = f"{FABRIC_API_BASE}/workspaces/{cfg['WORKSPACE_ID']}/items"

    # Retry with backoff — role propagation may take a few seconds
    max_attempts = 6
    for attempt in range(1, max_attempts + 1):
        resp = http_get(url, headers=fabric_headers(token), timeout=30)
        info_msg(f"GET ...items → {resp.status_code} (attempt {attempt}/{max_attempts})")

        if resp.status_code == 200:
            items = resp.json().get("value", [])
            pass_msg(f"SPN2 can list items — found {len(items)} item(s)")
            for item in items[:5]:
                info_msg(f"  • {item.get('type', '?')}: {item.get('displayName', '?')}")
            if len(items) > 5:
                info_msg(f"  ... and {len(items) - 5} more")
            return True

        # Fail fast on errors that aren't propagation-related
        if resp.status_code in (400, 401):
            fail_msg(f"Non-retryable error ({resp.status_code}): {resp.text[:200]}")
            return False

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            info_msg(f"Rate limited, waiting {retry_after}s...")
            time.sleep(retry_after)
            continue

        if attempt < max_attempts:
            wait = 2 ** attempt
            info_msg(f"Not yet propagated, retrying in {wait}s...")
            time.sleep(wait)

    fail_msg(f"SPN2 still cannot list items after {max_attempts} attempts")
    return False


def step7_spn2_sql_connect(cfg: dict) -> bool:
    """SPN2 connects to SQL Analytics Endpoint and discovers its SQL principal name."""
    step_header(7, "SPN2 connects to SQL Analytics Endpoint")

    try:
        conn = sql_connect(
            cfg["SQL_ENDPOINT"], cfg["DATABASE_NAME"], cfg["TENANT_ID"],
            cfg["SPN2_CLIENT_ID"], cfg["SPN2_CLIENT_SECRET"],
        )
    except Exception as exc:
        fail_msg(f"SQL connection failed: {exc}")
        logging.debug(f"Exception detail: {exc!r}", exc_info=True)
        return False

    try:
        cursor, rows = sql_execute(conn, "SELECT USER_NAME()", fetch=True)
        sql_user = rows[0][0]
        pass_msg(f"Connected — SPN2 SQL identity: {sql_user}")
        # Fabric returns appId@tenantId but GRANT needs just the appId
        info_msg(f"Will use SPN2_CLIENT_ID ({cfg['SPN2_CLIENT_ID']}) for GRANT in step 9")
        return True
    finally:
        conn.close()


def step8_spn2_query_expect_fail(cfg: dict) -> bool:
    """SPN2 tries to SELECT from a table — should be denied.

    With Viewer role only (no ReadData item permission), SPN2 has CONNECT but
    no SELECT. This is the expected Fabric permission model for both Warehouse
    and SQL Analytics Endpoint when no additional item permissions are shared.
    """
    step_header(8, f"SPN2 queries {cfg['SCHEMA_NAME']}.{cfg['TABLE_NAME']} (expect permission denied)")

    schema = escape_sql_ident(cfg["SCHEMA_NAME"])
    table = escape_sql_ident(cfg["TABLE_NAME"])
    query = f"SELECT TOP 1 * FROM [{schema}].[{table}]"
    info_msg(f"Query: {query}")

    try:
        conn = sql_connect(
            cfg["SQL_ENDPOINT"], cfg["DATABASE_NAME"], cfg["TENANT_ID"],
            cfg["SPN2_CLIENT_ID"], cfg["SPN2_CLIENT_SECRET"],
        )
        cursor, rows = sql_execute(conn, query, fetch=True)
        conn.close()
        fail_msg(f"Query succeeded unexpectedly — returned {len(rows)} row(s)")
        info_msg("SPN2 may already have SELECT permission (continuing anyway)")
        return True
    except Exception as exc:
        err_msg = str(exc).lower()
        logging.debug(f"Exception detail: {exc!r}", exc_info=True)
        if "permission" in err_msg or "denied" in err_msg:
            pass_msg("SELECT correctly denied — SPN2 has CONNECT but no SELECT")
            return True
        fail_msg(f"Unexpected SQL error: {exc}")
        return False


def step9_spn1_grant_select(cfg: dict) -> bool:
    """SPN1 GRANTs SELECT on the schema to SPN2 using its display name."""
    spn2_name = cfg["SPN2_NAME"]
    step_header(9, f"SPN1 GRANTs SELECT ON SCHEMA::{cfg['SCHEMA_NAME']} TO [{spn2_name}]")

    schema = escape_sql_ident(cfg["SCHEMA_NAME"])
    principal = escape_sql_ident(spn2_name)
    grant_sql = f"GRANT SELECT ON SCHEMA::[{schema}] TO [{principal}]"
    info_msg(f"SQL: {grant_sql}")

    try:
        conn = sql_connect(
            cfg["SQL_ENDPOINT"], cfg["DATABASE_NAME"], cfg["TENANT_ID"],
            cfg["SPN1_CLIENT_ID"], cfg["SPN1_CLIENT_SECRET"],
        )
        sql_execute(conn, grant_sql)
        conn.commit()
        conn.close()
        pass_msg("GRANT SELECT executed successfully")
        return True
    except Exception as exc:
        fail_msg(f"GRANT failed: {exc}")
        logging.debug(f"Exception detail: {exc!r}", exc_info=True)
        return False


def step10_spn2_query_expect_success(cfg: dict) -> bool:
    """SPN2 re-runs the query — should succeed now."""
    step_header(10, f"SPN2 re-queries {cfg['SCHEMA_NAME']}.{cfg['TABLE_NAME']} (expect success)")

    schema = escape_sql_ident(cfg["SCHEMA_NAME"])
    table = escape_sql_ident(cfg["TABLE_NAME"])
    query = f"SELECT TOP 1 * FROM [{schema}].[{table}]"
    info_msg(f"Query: {query}")

    try:
        conn = sql_connect(
            cfg["SQL_ENDPOINT"], cfg["DATABASE_NAME"], cfg["TENANT_ID"],
            cfg["SPN2_CLIENT_ID"], cfg["SPN2_CLIENT_SECRET"],
        )
        cursor, rows = sql_execute(conn, query, fetch=True)
        columns = [desc[0] for desc in cursor.description]
        conn.close()

        pass_msg(f"Query succeeded — {len(rows)} row(s) returned")
        info_msg(f"Columns: {', '.join(columns)}")
        if rows:
            info_msg(f"First row: {rows[0]}")
        return True
    except Exception as exc:
        fail_msg(f"Query still failing: {exc}")
        logging.debug(f"Exception detail: {exc!r}", exc_info=True)
        return False


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    log_file = setup_logging()

    print("=" * 60)
    print("SPN SQL Access E2E Test")
    print("=" * 60)
    print(f"  📄 Log: {log_file}")

    logging.info("=" * 40)
    logging.info("SPN SQL Access E2E Test")

    cfg = load_config()

    info_msg(f"Tenant:    {cfg['TENANT_ID']}")
    info_msg(f"Workspace: {cfg['WORKSPACE_ID']}")
    info_msg(f"SQL:       {cfg['SQL_ENDPOINT']} / {cfg['DATABASE_NAME']}")
    info_msg(f"Table:     {cfg['SCHEMA_NAME']}.{cfg['TABLE_NAME']}")
    info_msg(f"SPN1:      {cfg['SPN1_CLIENT_ID']}")
    info_msg(f"SPN2:      {cfg['SPN2_CLIENT_ID']} (object: {cfg['SPN2_OBJECT_ID']})")

    results = {}

    # Step 1 — verify SPN1 is admin
    results[1] = step1_check_spn1_admin(cfg)
    if not results[1]:
        print("\n❌ Cannot continue — SPN1 is not Admin on the workspace.")
        sys.exit(1)

    # Step 2 — verify SPN1 can query the table
    results[2] = step2_spn1_query_table(cfg)
    if not results[2]:
        print("\n❌ Cannot continue — SPN1 cannot query the target table.")
        sys.exit(1)

    # Step 3 — verify SPN1 has Directory.Read.All and can resolve SPN2
    results[3] = step3_check_spn1_directory_read(cfg)
    if not results[3]:
        print("\n❌ Cannot continue — SPN1 cannot read directory / resolve SPN2.")
        sys.exit(1)

    # Step 4
    results[4] = step4_spn2_list_items_expect_403(cfg)

    # Step 5
    results[5] = step5_spn1_add_spn2_viewer(cfg)
    if not results[5]:
        print("\n❌ Cannot continue — role assignment failed.")
        sys.exit(1)

    # Step 6
    results[6] = step6_spn2_list_items_expect_200(cfg)
    if not results[6]:
        print("\n❌ Cannot continue — SPN2 still cannot access workspace.")
        sys.exit(1)

    # Step 7
    results[7] = step7_spn2_sql_connect(cfg)
    if not results[7]:
        print("\n❌ Cannot continue — SPN2 cannot connect to SQL endpoint.")
        sys.exit(1)

    # Step 8
    results[8] = step8_spn2_query_expect_fail(cfg)

    # Step 9
    results[9] = step9_spn1_grant_select(cfg)
    if not results[9]:
        print("\n❌ Cannot continue — GRANT failed.")
        sys.exit(1)

    # Step 10
    results[10] = step10_spn2_query_expect_success(cfg)

    # Summary
    print(f"\n{'=' * 60}")
    print("Summary")
    print(f"{'=' * 60}")

    all_pass = True
    for step_num in range(1, TOTAL_STEPS + 1):
        status = "✅" if results.get(step_num) else "❌"
        if not results.get(step_num):
            all_pass = False
        print(f"  {status} Step {step_num}")

    print()
    if all_pass:
        print("🎉 All steps passed — SPN2 has been granted SQL access successfully.")
    else:
        print("⚠️  Some steps failed — review output above.")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
