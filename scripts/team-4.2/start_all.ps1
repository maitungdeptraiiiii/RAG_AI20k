<#
.SYNOPSIS
    Khoi chay toan bo he thong Just-ice & Contract Studio (Docker + Neo4j + Legal Graph + Web Server).
#>
$ErrorActionPreference = "Continue"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$AppDir = Join-Path $RepoRoot "app\team-4.2"
$Python = Join-Path $AppDir ".venv\Scripts\python.exe"
$EnvFile = Join-Path $AppDir ".env"

if (-not (Test-Path $Python)) {
    Write-Error "Khong thay Python venv tai $Python"
    exit 1
}

# Doc NEO4J_USER va NEO4J_PASSWORD tu app/team-4.2/.env
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*(NEO4J_USER|NEO4J_PASSWORD)\s*=\s*(.+?)\s*(#.*)?$') {
            $val = $Matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($Matches[1], $val, "Process")
        }
    }
}
if (-not $env:NEO4J_USER) { $env:NEO4J_USER = "neo4j" }

Set-Location $AppDir

Write-Host "[1/4] Kiem tra Docker Desktop..." -ForegroundColor Cyan
$null = cmd /c "docker info --format {{.ServerVersion}} >nul 2>&1"
if ($LASTEXITCODE -ne 0) {
    Write-Host "      Dang khoi dong Docker Desktop..." -ForegroundColor Yellow
    docker desktop start
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Khong khoi dong duoc Docker Desktop"
        exit 1
    }
}

Write-Host "[2/4] Khoi dong Neo4j..." -ForegroundColor Cyan
docker compose -f docker/neo4j-compose.yml up -d
if ($LASTEXITCODE -ne 0) {
    Write-Error "Khoi dong Neo4j that bai"
    exit 1
}

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        if ((Invoke-WebRequest -Uri "http://localhost:7474" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $ready) {
    Write-Warning "Neo4j chua phan hoi cong 7474 sau 60s, van tiep tuc kiem tra graph..."
}

Write-Host "[3/4] Dong bo do thi luat..." -ForegroundColor Cyan
& $Python -m rag.legal graph build

Write-Host "[4/4] Khoi chay Web Server tai http://127.0.0.1:8501 ..." -ForegroundColor Green
Write-Host "      - Chat Phap luat : http://127.0.0.1:8501/"
Write-Host "      - Contract Studio: http://127.0.0.1:8501/contract-studio/"
Write-Host "      - Do thi Hop dong: http://127.0.0.1:8501/contracts/ask"
Write-Host "      - Nap tai lieu   : http://127.0.0.1:8501/upload"
Write-Host "      - Duyet kho luat : http://127.0.0.1:8501/review"
Write-Host "      - Neo4j Browser  : http://localhost:7474/"

& $Python ui\server.py
