param(
    [string]$JiuwenHome = "$env:USERPROFILE\.jiuwenswarm",
    [string]$DeviceServiceUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"

$projectDir = $PSScriptRoot
$pythonPath = Join-Path $projectDir ".venv\Scripts\python.exe"
$serverPath = Join-Path $projectDir "lamp_mcp_server.py"
$skillSource = Join-Path $projectDir "jiuwenswarm\lamp-control\SKILL.md"
$configPath = Join-Path $JiuwenHome "config\config.yaml"
$skillDir = Join-Path $JiuwenHome "agent\workspace\skills\lamp-control"
$skillPath = Join-Path $skillDir "SKILL.md"

foreach ($requiredPath in @($pythonPath, $serverPath, $skillSource, $configPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required file not found: $requiredPath"
    }
}

$configText = [System.IO.File]::ReadAllText($configPath)
$emptyMcpPattern = '(?m)^mcp:\r?\n  servers: \[\]\r?$'
$emptyMcpMatches = [regex]::Matches($configText, $emptyMcpPattern)
$lampMcpIsRegistered = $configText -match '(?m)^    - name: lamp-control\r?$'

if (-not $lampMcpIsRegistered -and $emptyMcpMatches.Count -ne 1) {
    throw "The installer expected one empty mcp.servers block and made no changes."
}

$mcpBlock = @"
mcp:
  servers:
    - name: lamp-control
      enabled: true
      transport: stdio
      command: '$pythonPath'
      args: ['$serverPath']
      cwd: '$projectDir'
      env:
        DEVICE_SERVICE_URL: '$DeviceServiceUrl'
      timeout_s: 30
"@

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$configBackup = "$configPath.bak-$stamp"
Copy-Item -LiteralPath $configPath -Destination $configBackup

if (Test-Path -LiteralPath $skillPath -PathType Leaf) {
    Copy-Item -LiteralPath $skillPath -Destination "$skillPath.bak-$stamp"
} else {
    New-Item -ItemType Directory -Force $skillDir | Out-Null
}

if (-not $lampMcpIsRegistered) {
    $updatedConfig = [regex]::Replace($configText, $emptyMcpPattern, $mcpBlock)
    [System.IO.File]::WriteAllText(
        $configPath,
        $updatedConfig,
        [System.Text.UTF8Encoding]::new($false)
    )
}
Copy-Item -LiteralPath $skillSource -Destination $skillPath -Force

if ($lampMcpIsRegistered) {
    Write-Output "JiuwenSwarm lamp-control MCP was already registered; Skill updated."
} else {
    Write-Output "JiuwenSwarm lamp-control MCP configuration installed."
}
Write-Output "Config backup: $configBackup"
Write-Output "Restart JiuwenSwarm before testing the lamp tools."
