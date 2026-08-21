# docker-clean.ps1 — Prune unused Docker resources
# Usage: .\scripts\docker-clean.ps1 [-Full]

param(
    [switch]$Full
)

Write-Host "Docker cleanup starting..." -ForegroundColor Cyan

# Remove stopped containers
Write-Host "`n[1/4] Removing stopped containers..." -ForegroundColor Yellow
docker container prune -f

# Remove dangling images
Write-Host "`n[2/4] Removing dangling images..." -ForegroundColor Yellow
docker image prune -f

# Remove unused networks
Write-Host "`n[3/4] Removing unused networks..." -ForegroundColor Yellow
docker network prune -f

if ($Full) {
    # Full cleanup: remove ALL unused images, volumes, build cache
    Write-Host "`n[4/4] Full cleanup (unused images + volumes + build cache)..." -ForegroundColor Yellow
    docker system prune -a --volumes -f
    docker builder prune -a -f
} else {
    # Conservative: only remove build cache older than 24h
    Write-Host "`n[4/4] Removing build cache older than 24h..." -ForegroundColor Yellow
    docker builder prune -f --filter "until=24h"
}

# Show reclaimed space summary
Write-Host "`nDocker disk usage:" -ForegroundColor Green
docker system df

Write-Host "`nDone." -ForegroundColor Cyan
