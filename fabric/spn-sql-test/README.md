# spn-sql-test

End-to-end test that validates adding a Service Principal (SPN) to a Microsoft Fabric workspace and granting it SQL access through the Fabric permission model.

**SPN1** (workspace admin) adds **SPN2** as a Viewer, then grants SQL SELECT via T-SQL. The script verifies each permission layer works correctly.

## Prerequisites

- Python 3.10+
- Two Entra ID app registrations (SPN1 and SPN2) with client secrets
- SPN1 must be an **Admin** (or Member) on the target Fabric workspace
- SPN1's app registration needs **`Directory.Read.All`** (Microsoft Graph, Application permission, with admin consent) — required for Fabric SQL to resolve other principals during GRANT
- SPN2 must **not** already be assigned to the workspace (or the test will note the pre-existing access)
- Fabric admin setting: **"Service principals can use Fabric APIs"** must be enabled, with both SPNs in the allowed security group
- At least one table in the SQL Analytics Endpoint / Warehouse to query

## Setup

```bash
cd fabric/spn-sql-test
cp .env.example .env
# Edit .env with your values
uv pip install -r requirements.txt
python sql-spn-test.py
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `TENANT_ID` | Entra ID tenant GUID |
| `SPN1_CLIENT_ID` | App registration client ID for the admin SPN |
| `SPN1_CLIENT_SECRET` | Client secret for SPN1 |
| `SPN2_CLIENT_ID` | App registration client ID for the SPN being added |
| `SPN2_CLIENT_SECRET` | Client secret for SPN2 |
| `SPN2_OBJECT_ID` | **Enterprise Application** (Service Principal) object ID — see note below |
| `SPN2_NAME` | Display name of the SPN2 app registration (used in SQL GRANT) |
| `WORKSPACE_ID` | Fabric workspace GUID |
| `SQL_ENDPOINT` | SQL Analytics Endpoint hostname (e.g., `abc123.datawarehouse.fabric.microsoft.com`) |
| `DATABASE_NAME` | Display name of the Lakehouse or Warehouse (used as `Initial Catalog`) |
| `SCHEMA_NAME` | Schema containing the test table (typically `dbo`) |
| `TABLE_NAME` | Table to query in steps 8 and 10 |

> **⚠️ Finding SPN2_OBJECT_ID:** Go to **Entra ID → Enterprise Applications** (not App Registrations!) → search for your app → copy the **Object ID**. This is the *service principal* object ID. The Object ID shown on the App Registration page is a *different GUID* and will cause `PrincipalNotFound` errors.

## What It Tests

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | SPN1 checks its workspace role | Admin confirmed |
| 2 | SPN1 queries the target table | Success — table exists and is accessible |
| 3 | SPN1 looks up SPN2 via Microsoft Graph | Success — Directory.Read.All confirmed |
| 4 | SPN2 lists workspace items | 403 — no access yet |
| 5 | SPN1 adds SPN2 as Viewer | 201 — role assigned |
| 6 | SPN2 lists workspace items | 200 — access granted |
| 7 | SPN2 connects to SQL endpoint | Success — CONNECT via Viewer role |
| 8 | SPN2 queries a table | Permission denied — no SELECT |
| 9 | SPN1 GRANTs SELECT on schema to SPN2 | Success — admin has full SQL rights |
| 10 | SPN2 re-queries the table | Success — data returned |

## Example Output

```
============================================================
SPN SQL Access E2E Test
============================================================
  📄 Log: _logs/20260420201630.log
  ℹ️  Tenant:    <tenant-id>
  ℹ️  Workspace: <workspace-id>
  ...

────────────────────────────────────────────────────────────
Step 1/10: Verify SPN1 is Admin on the workspace
────────────────────────────────────────────────────────────
  ℹ️  SPN1 token acquired for Fabric API
  ℹ️  GET ...roleAssignments → 200
  ✅ PASS — SPN1 confirmed as Admin (principal: ..., appId: ...)

...

============================================================
Summary
============================================================
  ✅ Step 1
  ✅ Step 2
  ✅ Step 3
  ✅ Step 4
  ✅ Step 5
  ✅ Step 6
  ✅ Step 7
  ✅ Step 8
  ✅ Step 9
  ✅ Step 10

🎉 All steps passed — SPN2 has been granted SQL access successfully.
```

## Notes

- The script uses [`mssql-python`](https://github.com/microsoft/mssql-python) for SQL connections with access token authentication — no separate ODBC driver installation required.
- The script does **not** clean up after itself (SPN2 remains a Viewer, GRANT remains). Run cleanup manually or add a `--cleanup` flag in future.
- Role propagation after step 5 may take a few seconds — the script retries with exponential backoff.
- The GRANT in step 9 uses `SPN2_NAME` (display name) from the `.env` file.
- Full HTTP request/response and SQL statement logging is written to `_logs/` (gitignored).
