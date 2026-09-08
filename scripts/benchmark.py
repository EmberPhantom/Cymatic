#!/usr/bin/env python3
"""Performance benchmarks and regression tests for CYMATIC

Uses httpx by default (already in requirements). Falls back to aiohttp if available.
"""
import asyncio
import time
import statistics
import json
from datetime import datetime
from typing import Dict, List, Any

try:
    import aiohttp  # type: ignore
    HAS_AIOHTTP = True
except ImportError:
    aiohttp = None  # type: ignore
    HAS_AIOHTTP = False

import httpx
import structlog

logger = structlog.get_logger()


class BenchmarkRunner:
    """Run performance benchmarks for CYMATIC services."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results: Dict[str, List[float]] = {}

    async def _check_service_health_httpx(self, url: str, service_name: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except Exception as e:
            logger.warning(f"{service_name} not reachable: {e}")
            return False

    async def _check_service_health(self, url: str, service_name: str) -> bool:
        if HAS_AIOHTTP:
            try:
                timeout = aiohttp.ClientTimeout(total=5)  # type: ignore
                async with aiohttp.ClientSession() as session:  # type: ignore
                    async with session.get(url, timeout=timeout) as resp:  # type: ignore
                        return resp.status == 200  # type: ignore
            except Exception as e:
                logger.warning(f"{service_name} not reachable: {e}")
                return False
        else:
            return await self._check_service_health_httpx(url, service_name)

    async def benchmark_endpoint(
        self,
        method: str,
        endpoint: str,
        payload: dict | None = None,
        headers: dict | None = None,
        iterations: int = 100,
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        """Benchmark a single endpoint with proper error handling."""
        url = f"{self.base_url}{endpoint}"
        headers = headers or {}
        headers["Content-Type"] = "application/json"

        if HAS_AIOHTTP:
            return await self._benchmark_aiohttp(url, method, payload, headers, iterations, timeout)
        else:
            return await self._benchmark_httpx(url, method, payload, headers, iterations, timeout)

    async def _benchmark_httpx(
        self, url: str, method: str, payload: dict | None, headers: dict | None, iterations: int, timeout: float
    ) -> Dict[str, Any]:
        latencies: List[float] = []
        errors = 0
        consecutive_errors = 0
        endpoint = url.replace(self.base_url, "")
        async with httpx.AsyncClient(timeout=timeout) as client:
            for _ in range(iterations):
                start = time.perf_counter()
                try:
                    resp = await client.request(method, url, json=payload, headers=headers)
                    latency = (time.perf_counter() - start) * 1000
                    latencies.append(latency)
                    consecutive_errors = 0
                    if resp.status_code >= 400:
                        errors += 1
                except httpx.TimeoutException:
                    logger.warning(f"Timeout on {endpoint}")
                    errors += 1
                    consecutive_errors += 1
                except httpx.ConnectError:
                    logger.warning(f"Connection refused for {endpoint}")
                    errors += 1
                    consecutive_errors += 1
                except Exception as e:
                    logger.error(f"Request failed: {e}")
                    errors += 1
                    consecutive_errors += 1
                if consecutive_errors >= 3:
                    logger.warning(f"Too many consecutive errors for {endpoint}, stopping early")
                    break
        if not latencies:
            return {"error": "All requests failed", "endpoint": endpoint, "errors": errors}
        latencies.sort()
        return {
            "endpoint": endpoint,
            "method": method,
            "iterations": iterations,
            "attempted": len(latencies) + errors,
            "errors": errors,
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "mean_ms": statistics.mean(latencies),
            "median_ms": statistics.median(latencies),
            "p95_ms": latencies[int(len(latencies) * 0.95)] if latencies else 0,
            "p99_ms": latencies[int(len(latencies) * 0.99)] if latencies else 0,
            "std_dev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
            "success_rate": (iterations - errors) / iterations * 100,
        }

    async def _benchmark_aiohttp(
        self, url: str, method: str, payload: dict | None, headers: dict | None, iterations: int, timeout: float
    ) -> Dict[str, Any]:
        latencies: List[float] = []
        errors = 0
        consecutive_errors = 0
        endpoint = url.replace(self.base_url, "")
        timeout_cfg = aiohttp.ClientTimeout(total=timeout)  # type: ignore
        async with aiohttp.ClientSession() as session:  # type: ignore
            for _ in range(iterations):
                start = time.perf_counter()
                try:
                    async with session.request(method, url, json=payload, headers=headers, timeout=timeout_cfg) as resp:  # type: ignore
                        await resp.read()  # type: ignore
                        latency = (time.perf_counter() - start) * 1000  # ms
                        latencies.append(latency)
                        consecutive_errors = 0
                        if resp.status >= 400:  # type: ignore
                            errors += 1
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout on {endpoint}")
                    errors += 1
                    consecutive_errors += 1
                except Exception as e:
                    # aiohttp ClientConnectorError fallback when aiohttp not fully typed
                    if "Connector" in type(e).__name__:
                        logger.warning(f"Connection refused for {endpoint}")
                    else:
                        logger.error(f"Request failed: {e}")
                    errors += 1
                    consecutive_errors += 1
                if consecutive_errors >= 3:
                    logger.warning(f"Too many consecutive errors for {endpoint}, stopping early")
                    break
        if not latencies:
            return {"error": "All requests failed", "endpoint": endpoint, "errors": errors}
        latencies.sort()
        return {
            "endpoint": endpoint,
            "method": method,
            "iterations": iterations,
            "attempted": len(latencies) + errors,
            "errors": errors,
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "mean_ms": statistics.mean(latencies),
            "median_ms": statistics.median(latencies),
            "p95_ms": latencies[int(len(latencies) * 0.95)] if latencies else 0,
            "p99_ms": latencies[int(len(latencies) * 0.99)] if latencies else 0,
            "std_dev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
            "success_rate": (iterations - errors) / iterations * 100,
        }

    async def run_api_benchmarks(self) -> Dict[str, Any]:
        """Run all API benchmarks with service availability checks."""
        results: Dict[str, Any] = {}
        if not await self._check_service_health(f"{self.base_url}/health", "API"):
            return {"error": "API not reachable"}
        # health check via httpx path
        results["health_check"] = await self.benchmark_endpoint("GET", "/health", iterations=50)
        return results

    async def run_llm_router_benchmarks(self) -> Dict[str, Any]:
        """Benchmark LLM Router endpoints."""
        results: Dict[str, Any] = {}
        if not await self._check_service_health("http://localhost:8001/health", "LLM Router"):
            logger.warning("LLM Router not reachable, skipping LLM Router benchmarks")
            return {"error": "LLM Router not reachable"}
        # Need to benchmark via base_url override for llm-router
        orig_base = self.base_url
        self.base_url = "http://localhost:8001"
        try:
            results["health"] = await self.benchmark_endpoint("GET", "/health", iterations=50)
        finally:
            self.base_url = orig_base
        return results

    async def run_websocket_benchmark(
        self,
        session_id: int | None = None,
        token: str | None = None,
        iterations: int = 100,
    ) -> Dict[str, Any]:
        """Benchmark WebSocket connection and message latency."""
        if not HAS_AIOHTTP:
            return {"error": "WebSocket benchmark requires aiohttp"}
        if session_id is None or not token:
            return {
                "error": (
                    "WebSocket benchmark requires a published stream session and "
                    "access token"
                )
            }

        ws_url = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = f"{ws_url}/v1/stream/ws/{session_id}?type=benchmark&token={token}"
        latencies: List[float] = []
        errors = 0
        timeout = aiohttp.ClientTimeout(total=5)  # type: ignore[union-attr]

        async with aiohttp.ClientSession(timeout=timeout) as session:  # type: ignore[union-attr]
            try:
                async with session.ws_connect(ws_url) as websocket:  # type: ignore[union-attr]
                    for index in range(iterations):
                        started = time.perf_counter()
                        try:
                            await websocket.send_json({"type": "ping", "id": str(index)})
                            message = await websocket.receive()
                            if message.type != aiohttp.WSMsgType.TEXT:  # type: ignore[union-attr]
                                errors += 1
                                continue
                            latencies.append((time.perf_counter() - started) * 1000)
                        except Exception:
                            errors += 1
            except Exception as exc:
                return {"error": f"WebSocket unavailable: {exc}"}

        if not latencies:
            return {"error": "WebSocket benchmark received no successful messages", "errors": errors}
        return {
            "iterations": iterations,
            "successful": len(latencies),
            "errors": errors,
            "mean_ms": statistics.mean(latencies),
            "median_ms": statistics.median(latencies),
            "p95_ms": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))],
            "success_rate": len(latencies) / iterations * 100,
        }

    def generate_report(self, results: Dict[str, Any]) -> str:
        """Generate benchmark report."""
        report = "# CYMATIC Performance Benchmark Report\n"
        report += f"Generated: {datetime.now().isoformat()}\n\n"
        if not results or all("error" in r for r in results.values() if isinstance(r, dict)):
            report += "No benchmarks run (services not available).\n"
            return report
        for category, results_dict in results.items():
            report += f"## {category}\n\n"
            if isinstance(results_dict, dict):
                for endpoint, metrics in results_dict.items():
                    if isinstance(metrics, dict) and "error" not in metrics:
                        report += f"### {endpoint}\n"
                        report += f"- Iterations: {metrics.get('iterations', 'N/A')}\n"
                        report += f"- Mean Latency: {metrics.get('mean_ms', 0):.2f} ms\n"
                        report += f"- Median Latency: {metrics.get('median_ms', 0):.2f} ms\n"
                        report += f"- P95 Latency: {metrics.get('p95_ms', 0):.2f} ms\n"
                        report += f"- P99 Latency: {metrics.get('p99_ms', 0):.2f} ms\n"
                        report += f"- Success Rate: {metrics.get('success_rate', 0):.2f}%\n"
                        report += f"- Errors: {metrics.get('errors', 0)}\n\n"
        return report

    async def run_all_benchmarks(self) -> Dict[str, Any]:
        """Run all benchmarks and generate report."""
        logger.info("Starting performance benchmarks...")
        all_results: Dict[str, Any] = {}
        all_results["api"] = await self.run_api_benchmarks()
        all_results["llm_router"] = await self.run_llm_router_benchmarks()
        all_results["websocket"] = await self.run_websocket_benchmark()
        report = self.generate_report(all_results)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(f"benchmark_results_{timestamp}.json", "w") as f:
            json.dump(all_results, f, indent=2, default=str)
        with open(f"benchmark_report_{timestamp}.md", "w") as f:
            f.write(report)
        logger.info("Benchmarks completed")
        return all_results


async def main():
    runner = BenchmarkRunner("http://localhost:8000")
    results = await runner.run_all_benchmarks()
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
