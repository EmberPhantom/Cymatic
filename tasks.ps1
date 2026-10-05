# CYMATIC Windows task runner — mirrors Makefile targets for PowerShell,
# where GNU make is not on PATH. Usage:
#   .\tasks.ps1 <target> [-Service api]
# Targets: help dev infra-up infra-down infra-logs up-mock test test-api
#   test-worker test-llm docker-build docker-up docker-down docker-down-v
#   docker-logs docker-ps docker-shell docker-clean clean
param(
  [string]$Target = "help",
  [string]$Service = ""
)

$ErrorActionPreference = "Stop"
$Compose = @("docker", "compose", "-f", "infra/docker/docker-compose.yml")
$DevCompose = $Compose + @("-f", "infra/docker/docker-compose.dev.yml")
$MockCompose = $Compose + @("-f", "infra/docker/docker-compose.s3mock.yml")
$TestCompose = $Compose + @("--profile", "test")

function Invoke-Compose([string[]]$Cmd) {
  & $Cmd[0] $Cmd[1..($Cmd.Count - 1)]
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Target) {
  "help" {
    Write-Output "dev infra-up infra-down infra-logs up-mock | test test-api test-worker test-llm"
    Write-Output "docker-build docker-up docker-down docker-down-v docker-logs docker-ps docker-shell docker-clean | clean"
  }
  "dev" { Invoke-Compose ($DevCompose + @("up", "-d", "--build")) }
  "infra-up" { Invoke-Compose ($Compose + @("up", "-d", "--build")) }
  "infra-down" { Invoke-Compose ($Compose + @("down")) }
  "infra-logs" { Invoke-Compose ($Compose + @("logs", "-f")) }
  "up-mock" { Invoke-Compose ($MockCompose + @("up", "-d", "--build")) }
  "test" {
    New-Item -ItemType Directory -Path ./reports -Force | Out-Null
    Invoke-Compose ($TestCompose + @("run", "--rm", "--build", "test-api"))
    Invoke-Compose ($TestCompose + @("run", "--rm", "--build", "test-worker"))
    Invoke-Compose ($TestCompose + @("run", "--rm", "--build", "test-llm-router"))
    Write-Output "JUnit reports in ./reports/"
  }
  "test-api" { New-Item -ItemType Directory -Path ./reports -Force | Out-Null; Invoke-Compose ($TestCompose + @("run", "--rm", "--build", "test-api")) }
  "test-worker" { New-Item -ItemType Directory -Path ./reports -Force | Out-Null; Invoke-Compose ($TestCompose + @("run", "--rm", "--build", "test-worker")) }
  "test-llm" { New-Item -ItemType Directory -Path ./reports -Force | Out-Null; Invoke-Compose ($TestCompose + @("run", "--rm", "--build", "test-llm-router")) }
  "docker-build" { & docker buildx bake -f docker-bake.hcl; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
  "docker-up" { Invoke-Compose ($Compose + @("up", "-d", "--build")) }
  "docker-down" { Invoke-Compose ($Compose + @("down")) }
  "docker-down-v" { Invoke-Compose ($Compose + @("down", "-v", "--remove-orphans")) }
  "docker-logs" {
    if ($Service) { Invoke-Compose ($Compose + @("logs", "-f", $Service)) }
    else { Invoke-Compose ($Compose + @("logs", "-f")) }
  }
  "docker-ps" { Invoke-Compose ($Compose + @("ps")) }
  "docker-shell" {
    if (-not $Service) { Write-Output "Usage: .\tasks.ps1 docker-shell -Service api"; exit 1 }
    Invoke-Compose ($Compose + @("exec", $Service, "sh"))
  }
  "docker-clean" {
    & docker container prune -f; & docker image prune -f
    & docker network prune -f; & docker builder prune -f --filter "until=24h"
    & docker system df
  }
  "clean" {
    foreach ($d in @("services/api/__pycache__", "services/api/.pytest_cache",
        "services/worker/__pycache__", "services/worker/.pytest_cache",
        "services/llm-router/__pycache__", "services/llm-router/.pytest_cache",
        "apps/web/.next", "reports")) {
      if (Test-Path $d) { Remove-Item -Recurse -Force $d }
    }
  }
  default { Write-Output "Unknown target: $Target (try: .\tasks.ps1 help)"; exit 1 }
}
