#!/usr/bin/env python3
"""Performance benchmarks and regression tests for CYMATIC"""
import asyncio
import time
import statistics
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
import aiohttp
import structlog

logger = structlog.get_logger()


class BenchmarkRunner:
    """Run performance benchmarks for CYMATIC services."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results: Dict[str, List[float]] = {}
    
    async def _check_service_health(self, session: aiohttp.ClientSession, url: str, service_name: str) -> bool:
        """Check if a service is healthy and reachable."""
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with session.get(url, timeout=timeout) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning(f"{service_name} not reachable: {e}")
            return False
    
    async def benchmark_endpoint(
        self,
        session: aiohttp.ClientSession,
        method: str,
        endpoint: str,
        payload: dict = None,
        headers: dict = None,
        iterations: int = 100,
        timeout: float = 5.0
    ) -> Dict[str, Any]:
        """Benchmark a single endpoint with proper error handling."""
        latencies = []
        errors = 0
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        url = f"{self.base_url}{endpoint}"
        headers = headers or {}
        headers["Content-Type"] = "application/json"
        
        timeout = aiohttp.ClientTimeout(total=timeout)
        
        for i in range(iterations):
            start = time.perf_counter()
            try:
                async with session.request(method, url, json=payload, headers=headers, timeout=timeout) as resp:
                    await resp.read()
                    latency = (time.perf_counter() - start) * 1000  # ms
                    latencies.append(latency)
                    consecutive_errors = 0
                    
                    if resp.status >= 400:
                        errors += 1
            except asyncio.TimeoutError:
                logger.warning(f"Timeout on {endpoint}")
                errors += 1
                consecutive_errors += 1
            except aiohttp.ClientConnectorError:
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
            "p95_ms": latencies[int(len(latencies) * 0.95)],
            "p99_ms": latencies[int(len(latencies) * 0.99)],
            "std_dev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
            "success_rate": (iterations - errors) / iterations * 100
        }
    
    async def run_api_benchmarks(self) -> Dict[str, Any]:
        """Run all API benchmarks with service availability checks."""
        results = {}
        
        async with aiohttp.ClientSession() as session:
            # First check if API is reachable
            if not await self._check_service_health(session, f"{self.base_url}/health", "API"):
                return {"error": "API not reachable"}
            
            # Health check
            results["health_check"] = await self.benchmark_endpoint(
                session, "GET", "/health", iterations=50
            )
        
        return results
    
    async def run_llm_router_benchmarks(self) -> Dict[str, Any]:
        """Benchmark LLM Router endpoints."""
        results = {}
        
        # Check if LLM Router is reachable
        async with aiohttp.ClientSession() as test_session:
            if not await self._check_service_health(test_session, "http://localhost:8001/health", "LLM Router"):
                logger.warning("LLM Router not reachable, skipping LLM Router benchmarks")
                return {"error": "LLM Router not reachable"}
        
        async with aiohttp.ClientSession() as session:
            # Health check
            results["health"] = await self.benchmark_endpoint(
                session, "GET", "http://localhost:8001/health", iterations=50
            )
        
        return results
    
    async def run_websocket_benchmark(self, iterations: int = 100) -> Dict[str, Any]:
        """Benchmark WebSocket connection and message latency."""
        return {"note": "WebSocket benchmark not yet implemented"}
    
    def generate_report(self, results: Dict[str, Any]) -> str:
        """Generate benchmark report."""
        report = f"# CYMATIC Performance Benchmark Report\n"
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
        
        all_results = {}
        
        # API benchmarks
        all_results["api"] = await self.run_api_benchmarks()
        
        # LLM Router benchmarks
        all_results["llm_router"] = await self.run_llm_router_benchmarks()
        
        # WebSocket benchmarks
        all_results["websocket"] = await self.run_websocket_benchmark()
        
        # Generate report
        report = self.generate_report(all_results)
        
        # Save results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
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