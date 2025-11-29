#!/usr/bin/env python3
"""
Agent-Gear Performance Benchmark

Comprehensive benchmark suite with two modes:
- single: Tests all operations once (default)
- repeated: Tests repeated queries to show indexing advantage
"""

import asyncio
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import statistics

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================
# FILE GENERATORS (Polyglot project simulation)
# ============================================================

@dataclass(frozen=True)
class FileKind:
    name: str
    extension: str
    ratio: float
    generator: Callable[[int, int], str | bytes]
    subdir: str
    is_binary: bool = False


def _python_module(file_id: int, dir_idx: int) -> str:
    return f'''"""Module {file_id} in {dir_idx}."""
from typing import Optional

VERSION = "{file_id}.0.0"

def function_{file_id}(param: str) -> Optional[str]:
    """Process something."""
    # TODO: implement this
    if not param:
        return None
    return f"Result: {{param}}"

class Service{file_id}:
    """Service class."""
    def __init__(self, name: str):
        self.name = name

    def process(self, data: dict) -> dict:
        return {{"status": "ok", "input": data}}

    async def async_process(self, data: dict) -> dict:
        await asyncio.sleep(0)
        return self.process(data)
'''


def _typescript_module(file_id: int, dir_idx: int) -> str:
    return f'''// Module {file_id}
export type User{file_id} = {{
  id: number;
  name: string;
}};

export async function fetchUser{file_id}(): Promise<User{file_id}> {{
  // TODO: add caching
  return {{ id: {file_id}, name: "user-{file_id}" }};
}}
'''


def _json_config(file_id: int, dir_idx: int) -> str:
    return f'''{{"service": "api-{dir_idx}", "version": "{file_id}.0", "todo": "TODO: update config"}}'''


def _yaml_manifest(file_id: int, dir_idx: int) -> str:
    return f'''apiVersion: v1
kind: Config
metadata:
  name: config-{file_id}
spec:
  replicas: {2 + file_id % 3}
  # TODO: add resource limits
'''


def _markdown_doc(file_id: int, dir_idx: int) -> str:
    return f'''# Document {file_id}

## Overview
TODO: add documentation for module {file_id}.
'''


def _sql_query(file_id: int, dir_idx: int) -> str:
    return f'''-- Query {file_id}
SELECT * FROM users WHERE id = {file_id};
-- TODO: add index
'''


def _log_file(file_id: int, dir_idx: int) -> str:
    lines = [f"2024-01-01 12:00:{i:02d} INFO Processing request {file_id + i}" for i in range(20)]
    lines.append(f"2024-01-01 12:00:59 ERROR Timeout in module {file_id}")
    return "\n".join(lines) + "\n"


def _binary_blob(file_id: int, dir_idx: int) -> bytes:
    return os.urandom(512 + (file_id % 256))


POLYGLOT_PROFILE = [
    FileKind("module", ".py", 0.30, _python_module, "src"),
    FileKind("frontend", ".ts", 0.15, _typescript_module, "frontend"),
    FileKind("config", ".json", 0.10, _json_config, "config"),
    FileKind("infra", ".yaml", 0.10, _yaml_manifest, "infra"),
    FileKind("docs", ".md", 0.10, _markdown_doc, "docs"),
    FileKind("query", ".sql", 0.08, _sql_query, "sql"),
    FileKind("logs", ".log", 0.12, _log_file, "logs"),
    FileKind("assets", ".bin", 0.05, _binary_blob, "assets", is_binary=True),
]


def create_project(root: Path, num_files: int = 500, num_dirs: int = 30) -> dict:
    """Create a realistic polyglot project structure."""
    print(f"Creating polyglot project ({num_files} files, {num_dirs} dirs)...")

    # Distribute files across kinds
    counts = [int(num_files * k.ratio) for k in POLYGLOT_PROFILE]
    remainder = num_files - sum(counts)
    for i in range(remainder):
        counts[i % len(counts)] += 1

    created = 0
    for kind, count in zip(POLYGLOT_PROFILE, counts):
        for i in range(count):
            dir_idx = (created + i) % num_dirs
            dir_path = root / kind.subdir / f"dir_{dir_idx:02d}"
            dir_path.mkdir(parents=True, exist_ok=True)

            file_path = dir_path / f"{kind.name}_{i:03d}{kind.extension}"
            content = kind.generator(created, dir_idx)
            if kind.is_binary:
                file_path.write_bytes(content if isinstance(content, bytes) else content.encode())
            else:
                file_path.write_text(content)
            created += 1

    # Root files
    (root / "README.md").write_text("# Test Project\n")
    (root / "pyproject.toml").write_text('[project]\nname = "test"\n')

    # Large log file for read_lines testing
    log_path = root / "logs" / "app.log"
    log_path.parent.mkdir(exist_ok=True)
    with open(log_path, "w") as f:
        for i in range(10000):
            f.write(f"2024-01-01 12:00:{i%60:02d} INFO [mod_{i%10}] Request {i}\n")

    summary = ", ".join(f"{c}x{k.extension}" for k, c in zip(POLYGLOT_PROFILE, counts) if c)
    print(f"Created {created + 3} files: {summary}")

    return {"counts": dict(zip([k.extension for k in POLYGLOT_PROFILE], counts))}


# ============================================================
# BENCHMARK UTILITIES
# ============================================================

def bench(name: str, func: Callable, iterations: int = 5, warmup: int = 1) -> dict:
    """Run a benchmark."""
    for _ in range(warmup):
        func()

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = func()
        times.append((time.perf_counter() - start) * 1000)

    return {
        "name": name,
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "min": min(times),
        "max": max(times),
        "total": sum(times),
        "times": times,
        "result": len(result) if hasattr(result, "__len__") else result,
    }


# ============================================================
# SINGLE MODE: Test all operations once
# ============================================================

def run_single_benchmark(root: Path):
    """Run comprehensive single-pass benchmark."""
    from agent_gear import FileSystem, AsyncFileSystem
    import glob as std_glob

    results = {}

    # 1. INDEX BUILD
    print("\n" + "=" * 70)
    print("1. INDEX BUILD")
    print("=" * 70)
    start = time.perf_counter()
    fs = FileSystem(str(root), auto_watch=False)
    fs.wait_ready(timeout=60)
    index_time = (time.perf_counter() - start) * 1000
    print(f"Index build: {index_time:.1f}ms")
    results["index"] = index_time

    # 2. FILE LISTING
    print("\n" + "=" * 70)
    print("2. FILE LISTING")
    print("=" * 70)
    r = bench("ag.list", lambda: fs.list("**/*"))
    r_walk = bench("os.walk", lambda: [os.path.join(dp, f) for dp, dn, fn in os.walk(root) for f in fn])
    print(f"agent_gear.list():  {r['mean']:>6.2f}ms  ({r['result']} files)")
    print(f"os.walk():          {r_walk['mean']:>6.2f}ms  ({r_walk['result']} files)")
    print(f"Speedup: {r_walk['mean']/r['mean']:.1f}x")
    results["list"] = {"ag": r, "std": r_walk}

    # 3. GLOB PATTERNS
    print("\n" + "=" * 70)
    print("3. GLOB PATTERNS")
    print("=" * 70)
    patterns = [("**/*.py", "Python"), ("src/**/*.py", "src/"), ("**/*.md", "Markdown")]
    for pat, desc in patterns:
        r = bench(f"ag.glob({pat})", lambda p=pat: fs.glob(p))
        r_std = bench("std.glob", lambda p=pat: list(std_glob.glob(str(root / p), recursive=True)))
        speedup = r_std['mean'] / r['mean']
        print(f"{desc:10} ag:{r['mean']:>6.2f}ms  std:{r_std['mean']:>6.2f}ms  {speedup:.1f}x  ({r['result']})")
        results[f"glob_{pat}"] = {"ag": r, "std": r_std}

    # 4. FILE READING
    print("\n" + "=" * 70)
    print("4. FILE READING")
    print("=" * 70)
    py_files = fs.glob("**/*.py")[:50]

    r = bench("read_file", lambda: fs.read_file(py_files[0]))
    print(f"read_file():          {r['mean']:>6.3f}ms")

    r = bench("read_batch(50)", lambda: fs.read_batch(py_files))
    r_serial = bench("serial", lambda: {p: open(root / p).read() for p in py_files})
    print(f"read_batch(50):       {r['mean']:>6.2f}ms  (serial: {r_serial['mean']:.2f}ms)")
    results["read_batch"] = {"ag": r, "std": r_serial}

    r = bench("read_lines(0,100)", lambda: fs.read_lines("logs/app.log", 0, 100))
    print(f"read_lines(0,100):    {r['mean']:>6.3f}ms  ({r['result']} lines)")

    r = bench("read_lines(5000,100)", lambda: fs.read_lines("logs/app.log", 5000, 100))
    print(f"read_lines(5000,100): {r['mean']:>6.3f}ms")
    results["read_lines"] = r

    # 5. FILE WRITING
    print("\n" + "=" * 70)
    print("5. FILE WRITING")
    print("=" * 70)
    content = "Test line\n" * 100

    r_atomic = bench("write_file", lambda: fs.write_file("test_atomic.txt", content))
    r_fast = bench("write_file_fast", lambda: fs.write_file_fast("test_fast.txt", content))
    r_std = bench("std.write", lambda: open(root / "test_std.txt", "w").write(content))
    print(f"write_file (atomic):  {r_atomic['mean']:>6.2f}ms")
    print(f"write_file_fast:      {r_fast['mean']:>6.3f}ms  ({r_atomic['mean']/r_fast['mean']:.0f}x faster)")
    print(f"std open().write():   {r_std['mean']:>6.3f}ms")
    results["write"] = {"atomic": r_atomic, "fast": r_fast, "std": r_std}

    # 6. GREP SEARCH
    print("\n" + "=" * 70)
    print("6. GREP SEARCH")
    print("=" * 70)
    searches = [("TODO", "**/*.py"), ("def ", "**/*.py"), ("ERROR", "**/*.log")]
    for query, pat in searches:
        r = bench(f"grep({query})", lambda q=query, p=pat: fs.grep(q, p, max_results=500))
        print(f"grep '{query}' in {pat}: {r['mean']:>6.2f}ms  ({r['result']} matches)")
        results[f"grep_{query}"] = r

    try:
        r_sys = bench("sys grep", lambda: subprocess.run(
            ["grep", "-r", "-l", "TODO", "--include=*.py", str(root)],
            capture_output=True, text=True
        ).stdout.strip().split("\n"))
        print(f"system grep 'TODO':   {r_sys['mean']:>6.2f}ms  ({r_sys['result']} files)")
        results["sys_grep"] = r_sys
    except FileNotFoundError:
        pass

    # 7. ASYNC OPERATIONS
    print("\n" + "=" * 70)
    print("7. ASYNC OPERATIONS")
    print("=" * 70)

    async def async_bench():
        async with AsyncFileSystem(str(root)) as afs:
            await afs.wait_ready()

            start = time.perf_counter()
            await afs.list("**/*.py")
            await afs.grep("TODO", "**/*.py")
            await afs.read_lines("logs/app.log", 0, 100)
            seq = (time.perf_counter() - start) * 1000

            start = time.perf_counter()
            await asyncio.gather(
                afs.list("**/*.py"),
                afs.grep("TODO", "**/*.py"),
                afs.read_lines("logs/app.log", 0, 100),
            )
            conc = (time.perf_counter() - start) * 1000
            return seq, conc

    seq, conc = asyncio.run(async_bench())
    print(f"3 ops sequential:     {seq:>6.2f}ms")
    print(f"3 ops concurrent:     {conc:>6.2f}ms  ({seq/conc:.1f}x speedup)")
    results["async"] = {"seq": seq, "conc": conc}

    fs.close()
    return results


# ============================================================
# REPEATED MODE: Test repeated queries
# ============================================================

def run_repeated_benchmark(root: Path, num_queries: int = 20):
    """Benchmark repeated queries to show indexing advantage."""
    from agent_gear import FileSystem
    import glob as std_glob

    print("\n" + "=" * 70)
    print(f"REPEATED QUERY BENCHMARK ({num_queries} iterations)")
    print("=" * 70)

    # Agent-Gear
    print("\n--- Agent-Gear (with indexing) ---")
    start = time.perf_counter()
    fs = FileSystem(str(root), auto_watch=False)
    fs.wait_ready(timeout=60)
    index_time = (time.perf_counter() - start) * 1000
    print(f"Index build: {index_time:.1f}ms (one-time)")

    ag_results = {}
    ops = [
        ("list", lambda: fs.list("**/*")),
        ("glob *.py", lambda: fs.glob("**/*.py")),
        ("glob *.ts", lambda: fs.glob("**/*.ts")),
        ("grep TODO", lambda: fs.grep("TODO", "**/*.py", max_results=500)),
        ("grep ERROR", lambda: fs.grep("ERROR", "**/*.log", max_results=500)),
    ]

    for name, func in ops:
        times = []
        for _ in range(num_queries):
            start = time.perf_counter()
            result = func()
            times.append((time.perf_counter() - start) * 1000)
        ag_results[name] = {"times": times, "result": len(result) if hasattr(result, "__len__") else result}
        print(f"{name}: mean={statistics.mean(times):.2f}ms, total={sum(times):.1f}ms ({ag_results[name]['result']})")

    ag_query_total = sum(sum(r["times"]) for r in ag_results.values())
    print(f"\nAgent-Gear TOTAL: {ag_query_total:.1f}ms (excluding index)")
    fs.close()

    # Standard library
    print("\n--- Python Standard Library ---")
    std_results = {}

    std_ops = [
        ("os.walk", lambda: [os.path.join(dp, f) for dp, dn, fn in os.walk(root) for f in fn]),
        ("glob *.py", lambda: list(std_glob.glob(str(root / "**/*.py"), recursive=True))),
        ("glob *.ts", lambda: list(std_glob.glob(str(root / "**/*.ts"), recursive=True))),
        ("grep TODO", lambda: subprocess.run(["grep", "-r", "-l", "TODO", "--include=*.py", str(root)],
                                              capture_output=True, text=True).stdout.strip().split("\n")),
        ("grep ERROR", lambda: subprocess.run(["grep", "-r", "-l", "ERROR", "--include=*.log", str(root)],
                                               capture_output=True, text=True).stdout.strip().split("\n")),
    ]

    for name, func in std_ops:
        times = []
        for _ in range(num_queries):
            start = time.perf_counter()
            try:
                result = func()
            except Exception:
                result = []
            times.append((time.perf_counter() - start) * 1000)
        std_results[name] = {"times": times, "result": len(result) if hasattr(result, "__len__") else result}
        print(f"{name}: mean={statistics.mean(times):.2f}ms, total={sum(times):.1f}ms")

    std_total = sum(sum(r["times"]) for r in std_results.values())
    print(f"\nStdlib TOTAL: {std_total:.1f}ms")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY (excluding index build)")
    print("=" * 70)
    speedup = std_total / ag_query_total
    print(f"\nAgent-Gear: {ag_query_total:.1f}ms")
    print(f"Stdlib:     {std_total:.1f}ms")
    print(f"Speedup:    {speedup:.1f}x")

    print(f"\nPer-query comparison:")
    print(f"  {'Operation':<15} {'Agent-Gear':>12} {'Stdlib':>12} {'Speedup':>10}")
    print(f"  {'-' * 49}")
    for (ag_name, _), (std_name, _) in zip(ops, std_ops):
        ag_mean = statistics.mean(ag_results[ag_name]["times"])
        std_mean = statistics.mean(std_results[std_name]["times"])
        print(f"  {ag_name:<15} {ag_mean:>10.2f}ms {std_mean:>10.2f}ms {std_mean/ag_mean:>9.1f}x")

    # Amortization
    print(f"\nAmortization:")
    print(f"  Index cost: {index_time:.1f}ms (one-time)")
    savings_per_round = std_total - ag_query_total
    if savings_per_round > 0:
        rounds_to_break_even = index_time / savings_per_round
        print(f"  Savings per round: {savings_per_round:.1f}ms")
        print(f"  Break-even: ~{max(1, int(rounds_to_break_even))} rounds of {len(ops)} queries")


# ============================================================
# SUMMARY
# ============================================================

def print_summary(results: dict):
    """Print final summary table."""
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)

    data = []
    if "index" in results:
        data.append(("Index Build", f"{results['index']:.0f}ms", "-", "-"))
    if "list" in results:
        ag, std = results["list"]["ag"]["mean"], results["list"]["std"]["mean"]
        data.append(("List Files", f"{ag:.1f}ms", f"{std:.1f}ms", f"{std/ag:.1f}x"))
    if "glob_**/*.py" in results:
        ag, std = results["glob_**/*.py"]["ag"]["mean"], results["glob_**/*.py"]["std"]["mean"]
        data.append(("Glob **/*.py", f"{ag:.1f}ms", f"{std:.1f}ms", f"{std/ag:.1f}x"))
    if "grep_TODO" in results and "sys_grep" in results:
        ag, std = results["grep_TODO"]["mean"], results["sys_grep"]["mean"]
        data.append(("Grep TODO", f"{ag:.1f}ms", f"{std:.1f}ms", f"{std/ag:.1f}x"))
    if "write" in results:
        atomic, fast = results["write"]["atomic"]["mean"], results["write"]["fast"]["mean"]
        data.append(("Write (atomic)", f"{atomic:.1f}ms", "-", "-"))
        data.append(("Write (fast)", f"{fast:.2f}ms", "-", f"{atomic/fast:.0f}x faster"))
    if "async" in results:
        seq, conc = results["async"]["seq"], results["async"]["conc"]
        data.append(("Async (3 ops)", f"{conc:.1f}ms", f"{seq:.1f}ms (seq)", f"{seq/conc:.1f}x"))

    print(f"\n{'Operation':<18} {'Agent-Gear':<14} {'Baseline':<16} {'Note':<12}")
    print("-" * 60)
    for row in data:
        print(f"{row[0]:<18} {row[1]:<14} {row[2]:<16} {row[3]:<12}")


# ============================================================
# MAIN
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Agent-Gear Performance Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python benchmark.py                    # Single mode, 500 files
  python benchmark.py --files 2000       # Single mode, 2000 files
  python benchmark.py --mode repeated    # Repeated query mode
  python benchmark.py --mode all         # Run both modes
"""
    )
    parser.add_argument("--files", type=int, default=500, help="Number of files (default: 500)")
    parser.add_argument("--dirs", type=int, default=30, help="Number of directories (default: 30)")
    parser.add_argument("--mode", choices=["single", "repeated", "all"], default="single",
                        help="Benchmark mode (default: single)")
    parser.add_argument("--queries", type=int, default=20, help="Iterations for repeated mode (default: 20)")
    args = parser.parse_args()

    print("=" * 70)
    print("Agent-Gear Performance Benchmark")
    print(f"Mode: {args.mode} | Files: {args.files} | Dirs: {args.dirs}")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        create_project(root, args.files, args.dirs)

        if args.mode in ("single", "all"):
            results = run_single_benchmark(root)
            print_summary(results)

        if args.mode in ("repeated", "all"):
            run_repeated_benchmark(root, args.queries)


if __name__ == "__main__":
    main()
