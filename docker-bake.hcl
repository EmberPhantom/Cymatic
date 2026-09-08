# CYMATIC Docker Bake — parallel builds with GHA cache
# Replaces sequential `docker build` calls; runs 4 images in parallel via buildx.
# Usage: docker buildx bake -f docker-bake.hcl
# CI: automatically uses GHA cache (requires ACTIONS_CACHE_URL); local fallback skips gracefully.

group "default" {
  targets = ["api", "worker", "llm-router", "web"]
}

variable "NEXT_PUBLIC_API_URL" {
  default = "http://localhost:8000"
}
variable "NEXT_PUBLIC_WS_URL" {
  default = "ws://localhost:8000"
}
variable "NEXT_PUBLIC_MINIO_URL" {
  default = "http://localhost:9000"
}

target "api" {
  context    = "./services/api"
  dockerfile = "Dockerfile"
  contexts = {
    shared = "./packages/cymatic-shared"
  }
  target = "runtime"
  tags   = ["cymatic/api:latest"]
  cache-from = ["type=gha"]
  cache-to   = ["type=gha,mode=max"]
}

target "worker" {
  context    = "./services/worker"
  dockerfile = "Dockerfile"
  contexts = {
    shared = "./packages/cymatic-shared"
  }
  target = "runtime"
  tags   = ["cymatic/worker:latest"]
  cache-from = ["type=gha"]
  cache-to   = ["type=gha,mode=max"]
}

target "llm-router" {
  context    = "./services/llm-router"
  dockerfile = "Dockerfile"
  contexts = {
    shared = "./packages/cymatic-shared"
  }
  target = "runtime"
  tags   = ["cymatic/llm-router:latest"]
  cache-from = ["type=gha"]
  cache-to   = ["type=gha,mode=max"]
}

target "web" {
  context    = "./apps/web"
  dockerfile = "Dockerfile"
  tags       = ["cymatic/web:latest"]
  args = {
    NEXT_PUBLIC_API_URL   = "${NEXT_PUBLIC_API_URL}"
    NEXT_PUBLIC_WS_URL    = "${NEXT_PUBLIC_WS_URL}"
    NEXT_PUBLIC_MINIO_URL = "${NEXT_PUBLIC_MINIO_URL}"
  }
  cache-from = ["type=gha"]
  cache-to   = ["type=gha,mode=max"]
}
