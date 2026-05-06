<#
.SYNOPSIS
    Launch Microsoft Edge with Chrome DevTools Protocol (CDP) enabled.

.DESCRIPTION
    Starts Edge with --remote-debugging-port so that tools running in WSL
    (e.g. @playwright/mcp via Copilot CLI) can connect to the authenticated
    browser session and control it via CDP.

    Uses a separate user-data-dir so your normal Edge profile is unaffected.

.PARAMETER Port
    CDP debugging port. Default: 9222.

.PARAMETER Url
    Initial URL to open. Default: about:blank.

.PARAMETER UserDataDir
    Profile directory for the CDP instance.
    Default: $env:LOCALAPPDATA\edge-cdp-profile

.EXAMPLE
    .\Start-EdgeCDP.ps1
    .\Start-EdgeCDP.ps1 -Url "https://eng.ms"
    .\Start-EdgeCDP.ps1 -Port 9223 -Url "https://portal.azure.com"
#>

param(
    [int]$Port = 9222,
    [string]$Url = "about:blank",
    [string]$UserDataDir = "$env:LOCALAPPDATA\edge-cdp-profile"
)

$edgePaths = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
)

$edgeExe = $edgePaths | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $edgeExe) {
    Write-Error "Could not find msedge.exe. Is Edge installed?"
    exit 1
}

# Check if CDP port is already in use
$existing = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Port $Port is already in use — Edge CDP may already be running." -ForegroundColor Yellow
    Write-Host "CDP endpoint: http://localhost:$Port" -ForegroundColor Cyan
    Write-Host "Verify at:    http://localhost:$Port/json/version" -ForegroundColor Cyan
    exit 0
}

Write-Host "Starting Edge with CDP on port $Port..." -ForegroundColor Green
Write-Host "  Profile:  $UserDataDir" -ForegroundColor Gray
Write-Host "  URL:      $Url" -ForegroundColor Gray

$args = @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$UserDataDir",
    "--no-first-run",
    "--no-default-browser-check",
    $Url
)

Start-Process $edgeExe -ArgumentList $args

Start-Sleep -Seconds 2

# Verify CDP is listening
$check = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($check) {
    Write-Host "`nEdge CDP is running." -ForegroundColor Green
    Write-Host "CDP endpoint: http://localhost:$Port" -ForegroundColor Cyan
    Write-Host "Verify at:    http://localhost:$Port/json/version" -ForegroundColor Cyan
    Write-Host "`nNext steps:" -ForegroundColor Yellow
    Write-Host "  1. Log in to your internal site in this Edge window"
    Write-Host "  2. In WSL, Copilot CLI will connect via @playwright/mcp"
} else {
    Write-Warning "Edge started but CDP port $Port not detected yet. Give it a moment."
}
