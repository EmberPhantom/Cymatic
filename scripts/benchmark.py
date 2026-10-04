#!/usr/bin/env python3
"""Performance benchmarks and regression tests for CYMATIC

Uses httpx by default (already in requirements). Falls back to aiohttp if available.
"""
import argparse
import asyncio
import time
import statistics
import json
from datetime import datetime
from pathlib import Path
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

    def __init__(self, base_url: str = "http://localhost:8000", concurrency: int = 10):
        self.base_url = base_url
        # Default max in-flight requests for throughput measurement.
        self.concurrency = max(1, concurrency)
        self.results: Dict[str, List[float]] = {}

    async def _check_service_health_httpx(self, url: str, service_name: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except Exception as e:
            logger.warning("service_not_reachable", service=service_name, error=str(e))
            return False

    async def _check_service_health(self, url: str, service_name: str) -> bool:
        if HAS_AIOHTTP:
            try:
                timeout = aiohttp.ClientTimeout(total=5)  # type: ignore
                async with aiohttp.ClientSession() as session:  # type: ignore
                    async with session.get(url, timeout=timeout) as resp:  # type: ignore
                        return resp.status == 200  # type: ignore
            except Exception as e:
                logger.warning("service_not_reachable", service=service_name, error=str(e))
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
        concurrency: int | None = None,
    ) -> Dict[str, Any]:
        """Benchmark a single endpoint with proper error handling.

        Requests run concurrently (bounded by ``concurrency``) so the result
        reflects throughput, not just serial latency.
        """
        url = f"{self.base_url}{endpoint}"
        headers = headers or {}
        headers["Content-Type"] = "application/json"
        limit = self.concurrency if concurrency is None else max(1, concurrency)

        if HAS_AIOHTTP:
            return await self._benchmark_aiohttp(url, method, payload, headers, iterations, timeout, limit)
        else:
            return await self._benchmark_httpx(url, method, payload, headers, iterations, timeout, limit)

    async def _benchmark_httpx(
        self, url: str, method: str, payload: dict | None, headers: dict | None, iterations: int, timeout: float,
        concurrency: int = 10,
    ) -> Dict[str, Any]:
        """Concurrent httpx benchmark.

        Accounting: ``latencies`` holds ONLY 2xx/3xx responses; every HTTP
        >= 400 and every transport exception increments ``errors`` without
        appending a latency sample. So ``attempted == len(latencies) + errors
        == iterations`` (no double-count) and ``success_rate`` is exact.

        NOTE on early-break: the old serial loop aborted after 3 consecutive
        errors. That heuristic is removed deliberately — under concurrent
        gather there is no meaningful "consecutive" order, and aborting would
        under-sample throughput (the quantity being measured). A dead service
        fails fast anyway via the pre-flight health check in
        run_api_benchmarks/run_llm_router_benchmarks plus per-request
        timeouts; all failures surface in ``errors``/``success_rate``.
        """
        latencies: List[float] = []
        errors = 0
        endpoint = url.replace(self.base_url, "")
        sem = asyncio.Semaphore(max(1, concurrency))
        lock = asyncio.Lock()

        async def _one(client: httpx.AsyncClient) -> None:
            nonlocal errors
            async with sem:
                start = time.perf_counter()
                try:
                    resp = await client.request(method, url, json=payload, headers=headers)
                    latency = (time.perf_counter() - start) * 1000
                    if resp.status_code >= 400:
                        async with lock:
                            errors += 1
                    else:
                        async with lock:
                            latencies.append(latency)
                except httpx.TimeoutException:
                    logger.warning("request_timeout", endpoint=endpoint)
                    async with lock:
                        errors += 1
                except httpx.ConnectError:
                    logger.warning("connection_refused", endpoint=endpoint)
                    async with lock:
                        errors += 1
                except Exception as e:
                    logger.error("request_failed", endpoint=endpoint, error=str(e))
                    async with lock:
                        errors += 1

        async with httpx.AsyncClient(timeout=timeout) as client:
            await asyncio.gather(*(_one(client) for _ in range(iterations)))
        attempted = len(latencies) + errors
        if not latencies:
            return {"error": "All requests failed", "endpoint": endpoint, "errors": errors, "attempted": attempted}
        latencies.sort()
        successful = len(latencies)
        return {
            "endpoint": endpoint,
            "method": method,
            "iterations": iterations,
            "attempted": attempted,
            "errors": errors,
            "successful": successful,
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "mean_ms": statistics.mean(latencies),
            "median_ms": statistics.median(latencies),
            "p95_ms": latencies[min(successful - 1, int(successful * 0.95))],
            "p99_ms": latencies[min(successful - 1, int(successful * 0.99))],
            "std_dev_ms": statistics.stdev(latencies) if successful > 1 else 0,
            "success_rate": successful / attempted * 100 if attempted else 0.0,
        }

    async def _benchmark_aiohttp(
        self, url: str, method: str, payload: dict | None, headers: dict | None, iterations: int, timeout: float,
        concurrency: int = 10,
    ) -> Dict[str, Any]:
        """Concurrent aiohttp benchmark — same accounting/early-break policy
        as _benchmark_httpx (see its docstring)."""
        latencies: List[float] = []
        errors = 0
        endpoint = url.replace(self.base_url, "")
        sem = asyncio.Semaphore(max(1, concurrency))
        lock = asyncio.Lock()
        timeout_cfg = aiohttp.ClientTimeout(total=timeout)  # type: ignore

        async def _one(session) -> None:  # type: ignore[no-untyped-def]
            nonlocal errors
            async with sem:
                start = time.perf_counter()
                try:
                    async with session.request(method, url, json=payload, headers=headers, timeout=timeout_cfg) as resp:  # type: ignore
                        await resp.read()  # type: ignore
                        latency = (time.perf_counter() - start) * 1000  # ms
                        if resp.status >= 400:  # type: ignore
                            async with lock:
                                errors += 1
                        else:
                            async with lock:
                                latencies.append(latency)
                except asyncio.TimeoutError:
                    logger.warning("request_timeout", endpoint=endpoint)
                    async with lock:
                        errors += 1
                except Exception as e:
                    # aiohttp ClientConnectorError fallback when aiohttp not fully typed
                    if "Connector" in type(e).__name__:
                        logger.warning("connection_refused", endpoint=endpoint)
                    else:
                        logger.error("request_failed", endpoint=endpoint, error=str(e))
                    async with lock:
                        errors += 1

        async with aiohttp.ClientSession() as session:  # type: ignore
            await asyncio.gather(*(_one(session) for _ in range(iterations)))
        attempted = len(latencies) + errors
        if not latencies:
            return {"error": "All requests failed", "endpoint": endpoint, "errors": errors, "attempted": attempted}
        latencies.sort()
        successful = len(latencies)
        return {
            "endpoint": endpoint,
            "method": method,
            "iterations": iterations,
            "attempted": attempted,
            "errors": errors,
            "successful": successful,
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "mean_ms": statistics.mean(latencies),
            "median_ms": statistics.median(latencies),
            "p95_ms": latencies[min(successful - 1, int(successful * 0.95))],
            "p99_ms": latencies[min(successful - 1, int(successful * 0.99))],
            "std_dev_ms": statistics.stdev(latencies) if successful > 1 else 0,
            "success_rate": successful / attempted * 100 if attempted else 0.0,
        }

    async def run_api_benchmarks(self, iterations: int = 50, concurrency: int | None = None) -> Dict[str, Any]:
        """Run all API benchmarks with service availability checks."""
        results: Dict[str, Any] = {}
        if not await self._check_service_health(f"{self.base_url}/health", "API"):
            return {"error": "API not reachable"}
        # health check via httpx path
        results["health_check"] = await self.benchmark_endpoint(
            "GET", "/health", iterations=iterations, concurrency=concurrency
        )
        return results

    async def run_llm_router_benchmarks(self, iterations: int = 50, concurrency: int | None = None) -> Dict[str, Any]:
        """Benchmark LLM Router endpoints."""
        results: Dict[str, Any] = {}
        if not await self._check_service_health("http://localhost:8001/health", "LLM Router"):
            logger.warning("LLM Router not reachable, skipping LLM Router benchmarks")
            return {"error": "LLM Router not reachable"}
        # Need to benchmark via base_url override for llm-router
        orig_base = self.base_url
        self.base_url = "http://localhost:8001"
        try:
            results["health"] = await self.benchmark_endpoint(
                "GET", "/health", iterations=iterations, concurrency=concurrency
            )
        finally:
            self.base_url = orig_base
        return results

    async def run_websocket_benchmark(
        self,
        session_id: int | None = None,
        token: str | None = None,
        iterations: int = 100,
    ) -> Dict[str, Any]:
        """Benchmark WebSocket connection and message latency.

        Returns a ``{"skipped": reason}`` marker (NOT an error dict) when the
        benchmark cannot run — missing aiohttp or missing session
        credentials — so callers can omit the section instead of reporting
        a spurious failure.
        """
        if not HAS_AIOHTTP:
            return {"skipped": "WebSocket benchmark requires aiohttp"}
        if session_id is None or not token:
            return {
                "skipped": (
                    "WebSocket benchmark requires a published stream session and "
                    "access token (pass --ws-session-id/--ws-token); skipping"
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

        def _done(r: Any) -> bool:
            return isinstance(r, dict) and "error" not in r and "skipped" not in r

        if not results or not any(_done(r) for r in results.values() if isinstance(r, dict)):
            report += "No benchmarks run (services not available).\n"
            for category, results_dict in results.items():
                if isinstance(results_dict, dict) and "skipped" in results_dict:
                    report += f"- {category}: skipped ({results_dict['skipped']})\n"
            return report
        for category, results_dict in results.items():
            report += f"## {category}\n\n"
            if isinstance(results_dict, dict):
                if "skipped" in results_dict:
                    report += f"Skipped: {results_dict['skipped']}\n\n"
                    continue
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

    async def run_all_benchmarks(
        self,
        ws_session_id: int | None = None,
        ws_token: str | None = None,
        iterations: int = 50,
        concurrency: int | None = None,
    ) -> Dict[str, Any]:
        """Run all benchmarks and generate report.

        The websocket section is included ONLY when credentials are supplied;
        otherwise a ``{"skipped": ...}`` marker is recorded so the report
        shows a clean skip instead of a failure.
        """
        logger.info("Starting performance benchmarks...")
        all_results: Dict[str, Any] = {}
        all_results["api"] = await self.run_api_benchmarks(iterations=iterations, concurrency=concurrency)
        all_results["llm_router"] = await self.run_llm_router_benchmarks(iterations=iterations, concurrency=concurrency)
        if ws_session_id is None and not ws_token:
            all_results["websocket"] = {
                "skipped": "no --ws-session-id/--ws-token supplied; skipping websocket benchmark"
            }
        else:
            all_results["websocket"] = await self.run_websocket_benchmark(
                session_id=ws_session_id, token=ws_token, iterations=iterations * 2
            )
        report = self.generate_report(all_results)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(__file__).resolve().parents[1] / "reports"
        out_dir.mkdir(exist_ok=True)
        with open(out_dir / f"benchmark_results_{timestamp}.json", "w") as f:
            json.dump(all_results, f, indent=2, default=str)
        with open(out_dir / f"benchmark_report_{timestamp}.md", "w") as f:
            f.write(report)
        logger.info("Benchmarks completed")
        return all_results


async def main(argv: list | None = None):
    parser = argparse.ArgumentParser(description="CYMATIC performance benchmarks (concurrent throughput measurement).")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--iterations", type=int, default=50, help="Requests per endpoint")
    parser.add_argument("--concurrency", type=int, default=10, help="Max in-flight requests")
    parser.add_argument("--ws-session-id", type=int, default=None, help="Published stream session id for WS benchmark")
    parser.add_argument("--ws-token", default=None, help="Access token for WS benchmark")
    args = parser.parse_args(argv)

    runner = BenchmarkRunner(args.base_url, concurrency=args.concurrency)
    results = await runner.run_all_benchmarks(
        ws_session_id=args.ws_session_id,
        ws_token=args.ws_token,
        iterations=args.iterations,
        concurrency=args.concurrency,
    )
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
