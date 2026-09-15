# CYMATIC Docker Bake — parallel builds with local inline cache.
# Runs all 4 images in parallel via buildx (vs sequential `docker build`).
#
# Local:  docker buildx bake -f docker-bake.hcl        (inline cache, offline-friendly)
#          make docker-build
# CI:     docker buildx bake -f docker-bake.hcl -f docker-bake.ci.hcl
#          make docker-build-ci                         (GHA cache, needs ACTIONS_CACHE_URL)
#
# The GHA cache backend is intentionally CI-only: without ACTIONS_CACHE_URL it
# degrades to cold builds locally, which is why local defaults use `inline`.

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
  cache-from = ["type=inline"]
  cache-to   = ["type=inline"]
}

target "worker" {
  context    = "./services/worker"
  dockerfile = "Dockerfile"
  contexts = {
    shared = "./packages/cymatic-shared"
  }
  target = "runtime"
  tags   = ["cymatic/worker:latest"]
  cache-from = ["type=inline"]
  cache-to   = ["type=inline"]
}

target "llm-router" {
  context    = "./services/llm-router"
  dockerfile = "Dockerfile"
  contexts = {
    shared = "./packages/cymatic-shared"
  }
  target = "runtime"
  tags   = ["cymatic/llm-router:latest"]
  cache-from = ["type=inline"]
  cache-to   = ["type=inline"]
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
  cache-from = ["type=inline"]
  cache-to   = ["type=inline"]
}
