#!/usr/bin/env python3
import asyncio
import httpx
import time
import json
import statistics
from concurrent.futures import ThreadPoolExecutor
import sys


async def make_request(client, url, payload, results):
    start = time.time()
    try:
        response = await client.post(url, json=payload)
        latency = (time.time() - start) * 1000
        results.append({
            "status": response.status_code,
            "latency_ms": latency,
            "success": response.status_code == 200,
        })
    except Exception as e:
        latency = (time.time() - start) * 1000
        results.append({
            "status": 0,
            "latency_ms": latency,
            "success": False,
            "error": str(e),
        })


async def run_benchmark(url, total_requests, concurrency, payload):
    results = []
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_request(client):
        async with semaphore:
            await make_request(client, url, payload, results)

    print(f"\n{'='*60}")
    print(f"  Benchmark: {total_requests} requests, concurrency={concurrency}")
    print(f"{'='*60}")

    start_time = time.time()

    async with httpx.AsyncClient(timeout=60.0) as client:
        tasks = [bounded_request(client) for _ in range(total_requests)]
        await asyncio.gather(*tasks)

    total_time = time.time() - start_time

    latencies = [r["latency_ms"] for r in results]
    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.5)] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0

    report = {
        "total_requests": total_requests,
        "concurrency": concurrency,
        "total_time_seconds": round(total_time, 2),
        "rps": round(total_requests / total_time, 2) if total_time > 0 else 0,
        "success_count": len(successes),
        "failure_count": len(failures),
        "error_rate": round(len(failures) / total_requests * 100, 2) if total_requests > 0 else 0,
        "latency": {
            "min_ms": round(min(latencies), 2) if latencies else 0,
            "max_ms": round(max(latencies), 2) if latencies else 0,
            "avg_ms": round(statistics.mean(latencies), 2) if latencies else 0,
            "median_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "p99_ms": round(p99, 2),
            "stddev_ms": round(statistics.stdev(latencies), 2) if len(latencies) > 1 else 0,
        },
    }

    print(f"\n  Results:")
    print(f"  {'─'*50}")
    print(f"  RPS:              {report['rps']}")
    print(f"  Success:          {report['success_count']}")
    print(f"  Failures:         {report['failure_count']}")
    print(f"  Error Rate:       {report['error_rate']}%")
    print(f"  Total Time:       {report['total_time_seconds']}s")
    print(f"\n  Latency:")
    print(f"  {'─'*50}")
    print(f"  Min:    {report['latency']['min_ms']}ms")
    print(f"  Max:    {report['latency']['max_ms']}ms")
    print(f"  Avg:    {report['latency']['avg_ms']}ms")
    print(f"  Median: {report['latency']['median_ms']}ms")
    print(f"  P95:    {report['latency']['p95_ms']}ms")
    print(f"  P99:    {report['latency']['p99_ms']}ms")
    print(f"  StdDev: {report['latency']['stddev_ms']}ms")

    return report


async def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    url = f"{base_url}/v1/process"

    payload = {
        "action": "test",
        "data": {"key": "value", "timestamp": time.time()},
    }

    all_reports = []

    print("\n" + "=" * 60)
    print("  Proxy Service Benchmark")
    print("=" * 60)

    scenarios = [
        (100, 10),
        (500, 50),
        (1000, 100),
        (2000, 200),
    ]

    for total, concurrency in scenarios:
        report = await run_benchmark(url, total, concurrency, payload)
        all_reports.append(report)
        await asyncio.sleep(1)

    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"\n  {'Requests':<12} {'Concurrency':<12} {'RPS':<10} {'Avg(ms)':<10} {'P95(ms)':<10} {'Err%':<8}")
    print(f"  {'─'*62}")
    for r in all_reports:
        print(f"  {r['total_requests']:<12} {r['concurrency']:<12} {r['rps']:<10} "
              f"{r['latency']['avg_ms']:<10} {r['latency']['p95_ms']:<10} {r['error_rate']:<8}")

    with open("benchmark_results.json", "w") as f:
        json.dump(all_reports, f, indent=2)

    print(f"\n  Results saved to benchmark_results.json")


if __name__ == "__main__":
    asyncio.run(main())
