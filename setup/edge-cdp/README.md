# Edge CDP — Browser Control for Coding Agents

Connect coding agents (Copilot CLI, VS Code Copilot) to an authenticated Edge
browser session via Chrome DevTools Protocol. Designed for the DevBox WSL setup
where the agent runs in WSL but the browser runs on Windows.

## Why

Internal/auth-gated sites (eng.ms, SharePoint, Azure Portal) require Conditional
Access. MSAL tokens, cookie copying, and headless browsers all fail against CA.
The workaround: reuse a manually-authenticated Edge session via CDP.

## Architecture

```
Mac (SSH)
  └──▶ WSL (Copilot CLI)
         └──▶ @playwright/mcp (MCP server)
                └──▶ CDP http://localhost:9222
                       └──▶ Edge on Windows (your auth session)
```

## Setup

### 1. Windows side — launch Edge with CDP

```powershell
# From PowerShell on the DevBox (or double-click the script)
.\Start-EdgeCDP.ps1
.\Start-EdgeCDP.ps1 -Url "https://eng.ms"
```

Log in to the internal site in the Edge window that opens.

### 2. WSL networking

**Option A — mirrored networking (recommended):**

Add to `%USERPROFILE%\.wslconfig`:
```ini
[wsl2]
networkingMode=mirrored
```
Then `wsl --shutdown` and restart. `localhost` now works WSL → Windows.

**Option B — no config change:**

The `playwright-mcp-cdp.sh` wrapper auto-detects the Windows host IP.

### 3. WSL side — MCP config

#### With mirrored networking (Option A)

`~/.config/github-copilot/mcp.json`:
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest",
               "--cdp-endpoint", "http://localhost:9222"]
    }
  }
}
```

#### With host-IP auto-detection (Option B)

```json
{
  "mcpServers": {
    "playwright": {
      "command": "/home/lumolone/Developer/personal/lukes-toolbox/setup/edge-cdp/playwright-mcp-cdp.sh"
    }
  }
}
```

### 4. Verify

From WSL:
```bash
# Check CDP is reachable
curl -s http://localhost:9222/json/version | jq .Browser

# Start Copilot CLI — Playwright MCP tools should be available
copilot
/mcp   # lists connected MCP servers
```

## Per-Session Workflow

1. **RDP** into DevBox → run `Start-EdgeCDP.ps1`
2. **Log in** to the internal site in Edge (satisfies CA/MFA)
3. **SSH** from Mac → WSL → start Copilot CLI
4. Agent has full browser control with your cookies ✓

## Files

| File | Where | Purpose |
|------|-------|---------|
| `Start-EdgeCDP.ps1` | Windows | Launch Edge with CDP port |
| `playwright-mcp-cdp.sh` | WSL | MCP wrapper with auto host-IP detection |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `curl: Connection refused` on :9222 | Edge not running with CDP, or WSL can't reach Windows host |
| MCP connects but auth fails on site | You haven't logged in within the CDP Edge instance |
| Port already in use | Another Edge CDP instance is running — script will detect and report |
| WSL can't reach localhost:9222 | Enable `networkingMode=mirrored` or use the wrapper script |
