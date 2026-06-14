# Fabric SQL public-client Entra app

Python CLI for connecting to a Microsoft Fabric SQL Analytics Endpoint with a dedicated Microsoft Entra **public client** app registration instead of Azure CLI's first-party app ID.

The signed-in user remains the delegated SQL identity. The app registration is the OAuth client identity Entra records in token/sign-in evidence; Fabric SQL should still authorize and report the user principal.

> The directory name still says `obo-entra-appid` from the original idea. This implementation is intentionally public-client direct auth, not OBO.

## Architecture

```text
delegated user
  -> MSAL public client app registration
  -> delegated token for https://database.windows.net/
  -> mssql-python access-token injection
  -> Fabric SQL Analytics Endpoint
```

No confidential client, client secret, certificate, middle-tier API, or OBO exchange is used.

## Local setup

Use Python 3.12. The current `mssql-python` wheel imports cleanly on Python 3.12; Python 3.14 produced native driver issues during validation.

```bash
cd fabric/obo-entra-appid
cp .env.example .env
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

On macOS, install the native dependencies required by `mssql-python`:

```bash
brew install openssl unixodbc libtool
```

## Entra public client app

Set these shell variables before running the examples:

```bash
TENANT_ID="<tenant-id>"
PUBLIC_CLIENT_NAME="<app-display-name>"
SQL_RESOURCE_APP_ID="022907d3-0f1b-48f7-badc-1ba6abab6d66" # Azure SQL Database
```

Create the app registration:

```bash
PUBLIC_CLIENT_ID=$(az ad app create \
  --display-name "$PUBLIC_CLIENT_NAME" \
  --sign-in-audience AzureADMyOrg \
  --public-client-redirect-uris "http://localhost" \
  --query appId -o tsv)

az ad app update \
  --id "$PUBLIC_CLIENT_ID" \
  --set isFallbackPublicClient=true
```

Add delegated Azure SQL permission and grant admin consent:

```bash
SQL_SCOPE_ID=$(az ad sp show \
  --id "$SQL_RESOURCE_APP_ID" \
  --query "oauth2PermissionScopes[?value=='user_impersonation'].id | [0]" \
  -o tsv)

az ad app permission add \
  --id "$PUBLIC_CLIENT_ID" \
  --api "$SQL_RESOURCE_APP_ID" \
  --api-permissions "$SQL_SCOPE_ID=Scope"

az ad app permission admin-consent --id "$PUBLIC_CLIENT_ID"
```

The public client app must have:

- Redirect URI: `http://localhost`
- Public client flows enabled if device-code auth is required
- Delegated permission: Azure SQL Database `user_impersonation`
- Admin consent completed before the live run
- No client secret or certificate

## `.env` configuration

Populate `.env` with placeholders like:

```env
TENANT_ID=<tenant-id>
PUBLIC_CLIENT_ID=<public-client-app-id>
LOGIN_HINT=<delegated-user-upn>
PUBLIC_CLIENT_USERNAME=
PUBLIC_CLIENT_PASSWORD=
SQL_ENDPOINT=<fabric-sql-endpoint-hostname>
DATABASE_NAME=<warehouse-or-lakehouse-name>
DEFAULT_FLOW=interactive
MSAL_CACHE_PATH=.msal_token_cache.json
SQL_LOGIN_TIMEOUT_SECONDS=30
DEFAULT_QUERY=
```

Use `LOGIN_HINT` for test accounts so cached tokens cannot silently switch users.

`PUBLIC_CLIENT_USERNAME` and `PUBLIC_CLIENT_PASSWORD` are only for the test-only password flow described below. Do not store production credentials in `.env`.

## MFA-exempt test-user requirements

For a proof user that must avoid MFA registration, all of these must be true:

1. Per-user MFA state is disabled.
2. Security defaults are disabled.
3. Conditional Access MFA policies exclude the user or an exemption group containing the user.
4. Authentication Methods registration campaign excludes the user or an exemption group containing the user.
5. The user has Fabric workspace/item access and SQL permissions.

### Validate per-user MFA and security defaults

Azure CLI's own first-party app may not be preauthorized for the Graph policy scopes below. Use Microsoft Graph PowerShell for these checks:

```powershell
Connect-MgGraph `
  -TenantId "<tenant-id>" `
  -Scopes "Policy.Read.All", `
          "Policy.ReadWrite.AuthenticationMethod", `
          "Policy.ReadWrite.AuthenticationFlows", `
          "UserAuthenticationMethod.ReadWrite.All", `
          "Directory.Read.All" `
  -UseDeviceCode `
  -NoWelcome
```

Check per-user MFA:

```powershell
Invoke-MgGraphRequest `
  -Method GET `
  -Uri "https://graph.microsoft.com/beta/users/<user-id>/authentication/requirements"
```

Expected:

```json
{
  "perUserMfaState": "disabled"
}
```

Check security defaults:

```powershell
Invoke-MgGraphRequest `
  -Method GET `
  -Uri "https://graph.microsoft.com/v1.0/policies/identitySecurityDefaultsEnforcementPolicy"
```

Expected:

```json
{
  "isEnabled": false
}
```

### Validate Conditional Access MFA exclusions

```bash
USER_ID="<user-id>"

az rest \
  --method GET \
  --url "https://graph.microsoft.com/v1.0/identity/conditionalAccess/policies" \
  -o json \
  | jq -r --arg uid "$USER_ID" '
      .value[]
      | select((.grantControls.builtInControls // []) | index("mfa"))
      | [.displayName, (.conditions.users.excludeUsers // [] | index($uid) != null)]
      | @tsv'
```

Every enabled MFA policy that would otherwise target the user should show `true`, either by direct user exclusion or by equivalent group/role targeting.

### Exclude from Authentication Methods registration campaign

Create an exemption group and add the test user:

```bash
EXEMPT_GROUP_ID=$(az ad group create \
  --display-name "<mfa-registration-exemption-group-name>" \
  --mail-nickname "<mail-nickname>" \
  --query id -o tsv)

az rest \
  --method POST \
  --url "https://graph.microsoft.com/v1.0/groups/$EXEMPT_GROUP_ID/members/\$ref" \
  --headers "Content-Type=application/json" \
  --body "{\"@odata.id\":\"https://graph.microsoft.com/v1.0/directoryObjects/<user-id>\"}"
```

Patch the registration campaign to exclude that group:

```powershell
$ExemptGroupId = "<exemption-group-id>"

Connect-MgGraph -TenantId "<tenant-id>" -NoWelcome

$policy = Invoke-MgGraphRequest `
  -Method GET `
  -Uri "https://graph.microsoft.com/beta/policies/authenticationMethodsPolicy"

$campaign = $policy.registrationEnforcement.authenticationMethodsRegistrationCampaign
$excludeTargets = @()
if ($campaign.excludeTargets) {
  $excludeTargets = @($campaign.excludeTargets)
}
if (-not ($excludeTargets | Where-Object { $_.id -eq $ExemptGroupId })) {
  $excludeTargets += @{ id = $ExemptGroupId; targetType = "group" }
}

$body = @{
  registrationEnforcement = @{
    authenticationMethodsRegistrationCampaign = @{
      snoozeDurationInDays = $campaign.snoozeDurationInDays
      enforceRegistrationAfterAllowedSnoozes = $campaign.enforceRegistrationAfterAllowedSnoozes
      state = $campaign.state
      includeTargets = $campaign.includeTargets
      excludeTargets = $excludeTargets
    }
  }
} | ConvertTo-Json -Depth 20

Invoke-MgGraphRequest `
  -Method PATCH `
  -Uri "https://graph.microsoft.com/beta/policies/authenticationMethodsPolicy" `
  -Body $body `
  -ContentType "application/json"
```

Validate the campaign:

```powershell
$updated = Invoke-MgGraphRequest `
  -Method GET `
  -Uri "https://graph.microsoft.com/beta/policies/authenticationMethodsPolicy"

$updated.registrationEnforcement.authenticationMethodsRegistrationCampaign |
  ConvertTo-Json -Depth 20
```

Expected:

```json
{
  "includeTargets": [
    {
      "id": "all_users",
      "targetType": "group",
      "targetedAuthenticationMethod": "microsoftAuthenticator"
    }
  ],
  "excludeTargets": [
    {
      "id": "<exemption-group-id>",
      "targetType": "group"
    }
  ]
}
```

## Run the proof

Clear cache before changing users:

```bash
.venv/bin/python fabric_sql_public_client.py cache-clear
```

Run the diagnostic:

```bash
.venv/bin/python fabric_sql_public_client.py diagnose
```

Run an explicit query:

```bash
.venv/bin/python fabric_sql_public_client.py query --sql "SELECT 1 AS [ok]"
```

Use device code only when browser auth is unsuitable:

```bash
.venv/bin/python fabric_sql_public_client.py diagnose --flow device-code
```

Use password flow only for a controlled MFA-exempt proof account:

```bash
PUBLIC_CLIENT_USERNAME="<test-user-upn>" \
PUBLIC_CLIENT_PASSWORD="<test-user-password>" \
.venv/bin/python fabric_sql_public_client.py diagnose --flow password --no-cache
```

This uses MSAL's username/password grant (ROPC). It is intentionally supported for proof testing only. It fails when MFA, Conditional Access step-up, password reset, federation restrictions, Terms of Use, or passwordless requirements apply.

## Expected token evidence

The diagnostic prints safe, unverified token claims. For an MFA-exempt delegated test user, expect:

```json
{
  "aud": "https://database.windows.net",
  "appid": "<public-client-app-id>",
  "scp": "user_impersonation",
  "idtyp": "user",
  "amr": ["pwd"],
  "upn": "<delegated-user-upn>"
}
```

Key interpretation:

- `appid` proves the custom public client app was used instead of Azure CLI.
- `aud` proves the token is for Azure SQL/Fabric SQL.
- `amr: ["pwd"]` proves no MFA claim was issued.
- SQL identity diagnostics should return the delegated user, not the app registration.

For password-flow validation, also use `--no-cache` so the run proves a fresh non-interactive username/password token acquisition rather than reusing a cached interactive token.

## End-to-end success criteria

The proof is complete when all of these are true in the same run:

1. `diagnose --flow password --no-cache` acquires a token without browser or device-code interaction.
2. Token claims show:
   - `appid` is the custom public client app ID.
   - `aud` is `https://database.windows.net`.
   - `scp` includes `user_impersonation`.
   - `idtyp` is `user`.
   - `amr` is `["pwd"]`.
   - `upn` or `unique_name` is the expected delegated test user.
3. SQL identity diagnostics return the same delegated test user.
4. A simple query succeeds:

   ```bash
   PUBLIC_CLIENT_USERNAME="<test-user-upn>" \
   PUBLIC_CLIENT_PASSWORD="<test-user-password>" \
   .venv/bin/python fabric_sql_public_client.py query \
     --flow password \
     --no-cache \
     --sql "SELECT 1 AS [ok]"
   ```

Expected query shape:

```text
ok
--
1
```

## Fabric SQL access validation

The diagnostic identity query is:

```sql
SELECT
  SUSER_SNAME() AS [suser_sname],
  USER_NAME() AS [user_name],
  CURRENT_USER AS [current_user];
```

Notes:

- `ORIGINAL_LOGIN()` is not supported in Fabric SQL Analytics Endpoint.
- Bracket the `CURRENT_USER` alias because `current_user` is a keyword.
- If token acquisition succeeds but SQL login fails, fix Fabric workspace/item/SQL permissions for the delegated user.

## Failure guide

| Symptom | Likely cause |
| --- | --- |
| `AADSTS65001` | Azure SQL Database `user_impersonation` is not consented for the public client app. |
| `AADSTS50079` | The user is still required to register MFA; check per-user MFA, Security Defaults, CA MFA policies, and Authentication Methods registration campaign. |
| `AADSTS50126` | Invalid username/password or the password needs reset. |
| Password flow fails but interactive works | ROPC is blocked by tenant policy, federation, MFA/step-up, Terms of Use, or another interactive requirement. |
| Device code blocked, interactive works | Conditional Access likely blocks device-code flow. Use interactive browser. |
| Token claims show Azure CLI app ID | Wrong client ID/config/cache. Clear cache and check `.env`. |
| Token succeeds, SQL login fails | The delegated user lacks Fabric workspace/item access or SQL permissions. |
| TCP `0x102` | TCP 1433 to the Fabric endpoint timed out. Check VPN, firewall, and Fabric/SQL service tag allowlists. |

## Security notes

- Password flow is test-only and exists solely to prove a non-interactive MFA-exempt account path.
- Do not use ROPC/password auth for production or real automation.
- Do not store service-account passwords in the repo.
- Raw access tokens, refresh tokens, Authorization headers, and secrets are not printed.
- `.msal_token_cache.json` can contain refresh tokens and is gitignored.
- Use `--no-cache` to avoid reading/writing the persistent MSAL cache for a run.
- If multiple accounts are present in the cache, set `LOGIN_HINT` or pass `--login-hint`.
- When `LOGIN_HINT` is set, the CLI verifies the returned token's user claim before opening SQL.
- Arbitrary SQL support is local developer convenience only; do not expose this CLI as a service.
