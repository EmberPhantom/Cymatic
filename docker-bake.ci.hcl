# CYMATIC Docker Bake — CI override (GHA cache).
# Merged on top of docker-bake.hcl in CI only:
#   docker buildx bake -f docker-bake.hcl -f docker-bake.ci.hcl
# Requires ACTIONS_CACHE_URL / ACTIONS_RUNTIME_TOKEN (setup-buildx provides them).
# Do NOT use locally — without those vars every build goes cold.

target "api" {
  cache-from = ["type=gha"]
  cache-to   = ["type=gha,mode=max"]
}

target "worker" {
  cache-from = ["type=gha"]
  cache-to   = ["type=gha,mode=max"]
}

target "llm-router" {
  cache-from = ["type=gha"]
  cache-to   = ["type=gha,mode=max"]
}

target "web" {
  cache-from = ["type=gha"]
  cache-to   = ["type=gha,mode=max"]
}
