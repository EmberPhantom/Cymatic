# docker-clean.ps1 — Prune unused Docker resources safely
# Usage: .\scripts\docker-clean.ps1 [-Full]
#  -Full : also removes unused volumes and all build cache (destructive)

param(
    [switch]$Full
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Docker cleanup starting..." -ForegroundColor Cyan

function Invoke-Docker($args) {
    try {
        & docker @args
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "docker $args exited with $LASTEXITCODE"
        }
    } catch {
        Write-Warning "docker $args failed: $_"
    }
}

# Remove stopped containers
Write-Host "`n[1/4] Removing stopped containers..." -ForegroundColor Yellow
Invoke-Docker @("container", "prune", "-f")

# Remove dangling images
Write-Host "`n[2/4] Removing dangling images..." -ForegroundColor Yellow
Invoke-Docker @("image", "prune", "-f")

# Remove unused networks
Write-Host "`n[3/4] Removing unused networks..." -ForegroundColor Yellow
Invoke-Docker @("network", "prune", "-f")

if ($Full) {
    # Full cleanup: remove ALL unused images, volumes, build cache — explicit, destructive
    Write-Host "`n[4/4] Full cleanup (unused images + volumes + build cache)..." -ForegroundColor Yellow
    Write-Warning "This will remove volumes (DB data will be lost unless backed up). Continue? (y/N)"
    $resp = Read-Host
    if ($resp -eq "y" -or $resp -eq "Y") {
        Invoke-Docker @("system", "prune", "-a", "--volumes", "-f")
        Invoke-Docker @("builder", "prune", "-a", "-f")
    } else {
        Write-Host "Skipped full prune." -ForegroundColor Cyan
    }
} else {
    # Conservative: only remove build cache older than 24h (preserves volumes)
    Write-Host "`n[4/4] Removing build cache older than 24h (preserves volumes)..." -ForegroundColor Yellow
    Invoke-Docker @("builder", "prune", "-f", "--filter", "until=24h")
}

# Show reclaimed space summary
Write-Host "`nDocker disk usage:" -ForegroundColor Green
try { docker system df } catch { Write-Warning "docker system df failed: $_" }

Write-Host "`nDone. Volumes preserved unless -Full was used with confirmation." -ForegroundColor Cyan
