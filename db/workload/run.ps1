<#
.SYNOPSIS
  Runs a pgbench workload against the shop database inside the Docker container.

.DESCRIPTION
  pgbench is installed in the postgres:17 image, not on the host, so the scripts are copied into the container and run there.
  Write scenarios ROLL BACK unless -Commit is given, so by default no data changes (sequences and dead rows still do).

.EXAMPLE
  .\db\workload\run.ps1 -Scenario browse -Seconds 20 -Clients 8
  .\db\workload\run.ps1 -Scenario deadlock -Seconds 15
  .\db\workload\run.ps1 -Scenario orders -Seconds 20 -Clients 4 -Commit    # really inserts orders: ask first
#>
param(
    [ValidateSet('browse', 'orders', 'hot', 'deadlock', 'mixed')]
    [string]$Scenario = 'browse',
    [int]$Seconds = 20,
    [int]$Clients = 8,
    [switch]$Commit,
    [switch]$KeepStats   # by default pg_stat_statements is reset first so the report shows only this run
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root

# Read passwords from .env (never printed).
$env_ = @{}
Get-Content .env | Where-Object { $_ -match '^\s*[A-Z_]+=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    $env_[$k.Trim()] = $v.Trim()
}
$passwords = @{
    mcp_reader = $env_['MCP_READER_PASSWORD']
    shop_owner = $env_['SHOP_OWNER_PASSWORD']
    loader     = $env_['LOADER_PASSWORD']
}

# Copy the scripts into the container (the compose file does not mount db/workload).
docker compose cp db/workload db:/tmp/ | Out-Null

$commitFlag = if ($Commit) { 1 } else { 0 }
if (-not $KeepStats) {
    docker compose exec -T db psql -U postgres -d shop -qc "SELECT pg_stat_statements_reset()" | Out-Null
}

function Get-PgbenchArgs([string]$Role, [string[]]$Files, [int]$C) {
    $j = [Math]::Min($C, 4)
    $fileArgs = $Files | ForEach-Object { '-f'; "/tmp/workload/$_" }
    # -n: skip the built-in vacuum of pgbench tables (they do not exist here); -r: per-statement latency; -P 5: progress every 5 s
    @('compose', 'exec', '-T', '-e', "PGPASSWORD=$($passwords[$Role])", 'db', 'pgbench', '-h', '127.0.0.1', '-U', $Role, '-d', 'shop',
      '-n', '-r', '-P', '5', '-T', $Seconds, '-c', $C, '-j', $j, '-D', "commit=$commitFlag", '--failures-detailed') + $fileArgs
}

function Invoke-Pgbench([string]$Role, [string[]]$Files, [int]$C) {
    $a = Get-PgbenchArgs $Role $Files $C
    & docker @a
}

Write-Host "Scenario '$Scenario', $Seconds s, commit=$commitFlag" -ForegroundColor Cyan
switch ($Scenario) {
    'browse'   { Invoke-Pgbench 'mcp_reader' @('browse_read.sql') $Clients }
    'orders'   { Invoke-Pgbench 'shop_owner' @('place_order.sql') $Clients }
    'hot'      { Invoke-Pgbench 'loader' @('hot_inventory.sql') $Clients }
    'deadlock' { Invoke-Pgbench 'loader' @('deadlock_a.sql', 'deadlock_b.sql') 2 }
    'mixed' {
        # Different roles need separate pgbench processes; run them at the same time as background jobs.
        $reads = [Math]::Max(1, [int]($Clients * 0.7)); $writes = [Math]::Max(1, $Clients - $reads)
        $readArgs = Get-PgbenchArgs 'mcp_reader' @('browse_read.sql') $reads
        $writeArgs = Get-PgbenchArgs 'shop_owner' @('place_order.sql') $writes
        $jobs = @(
            Start-Job { param($d, $a) Set-Location $d; & docker @a 2>&1 } -ArgumentList $root, (, $readArgs)
            Start-Job { param($d, $a) Set-Location $d; & docker @a 2>&1 } -ArgumentList $root, (, $writeArgs)
        )
        $names = 'browse (mcp_reader)', 'orders (shop_owner)'
        for ($i = 0; $i -lt $jobs.Count; $i++) {
            Write-Host "---- $($names[$i]) ----" -ForegroundColor Cyan
            $jobs[$i] | Wait-Job | Receive-Job
        }
        $jobs | Remove-Job
    }
}
