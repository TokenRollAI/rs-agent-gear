# Agent-Gear

High-performance filesystem operations for AI agents, powered by Rust.

## Features

- **Stateful Indexing**: In-memory file tree with LRU-cached glob patterns
- **Batch I/O**: Parallel file read/write with smart threshold optimization
- **High-Performance Search**: Grep with parallel search and mmap for large files
- **Atomic Writes**: Safe file modifications with temp-fsync-rename pattern
- **Fast Writes**: Optional non-atomic mode for 30x faster writes
- **Large File Support**: Efficient line-based reading for logs and large files
- **Async Support**: Full async/await API with `AsyncFileSystem`
- **File Watching**: Real-time filesystem monitoring with event debouncing

## Installation

```bash
pip install agent-gear
```

For development:
```bash
git clone https://github.com/anthropics/agent-gear
cd agent-gear
pip install maturin
maturin develop --release
```

## Quick Start

```python
from agent_gear import FileSystem

with FileSystem("/path/to/project") as fs:
    fs.wait_ready()

    # List and glob
    all_files = fs.list("**/*")
    py_files = fs.glob("**/*.py")

    # Search with grep
    results = fs.grep("TODO", "**/*.py")
    for r in results:
        print(f"{r.file}:{r.line_number}: {r.content}")

    # Read files
    content = fs.read_file("main.py")
    batch = fs.read_batch(py_files[:10])

    # Large file: read specific lines
    lines = fs.read_lines("app.log", start_line=1000, count=100)

    # Write files
    fs.write_file("output.txt", content)      # Atomic (safe)
    fs.write_file_fast("temp.txt", content)   # Fast (30x faster)

    # Edit in place
    fs.edit_replace("config.py", "DEBUG = False", "DEBUG = True")
```

### Async Usage

```python
from agent_gear import AsyncFileSystem
import asyncio

async def main():
    async with AsyncFileSystem("/path/to/project") as fs:
        await fs.wait_ready()

        # All operations are async
        files = await fs.list("**/*.py")
        results = await fs.grep("TODO", "**/*.py")

        # Concurrent operations
        results = await asyncio.gather(
            fs.list("**/*.py"),
            fs.grep("def main"),
            fs.read_file("README.md"),
        )

asyncio.run(main())
```

## API Reference

### FileSystem

```python
class FileSystem:
    def __init__(self, root: str, auto_watch: bool = True) -> None: ...

    # Listing
    def list(self, pattern: str = "**/*", only_files: bool = True) -> list[str]: ...
    def glob(self, pattern: str) -> list[str]: ...

    # Reading
    def read_file(self, path: str, encoding: str = "utf-8") -> str: ...
    def read_batch(self, paths: list[str]) -> dict[str, str]: ...
    def read_lines(self, path: str, start_line: int = 0, count: int | None = None) -> list[str]: ...
    def read_file_range(self, path: str, offset: int, limit: int) -> str: ...

    # Writing
    def write_file(self, path: str, content: str) -> bool: ...           # Atomic
    def write_file_fast(self, path: str, content: str) -> bool: ...      # Fast
    def edit_replace(self, path: str, old_text: str, new_text: str, strict: bool = True) -> bool: ...

    # Searching
    def grep(self, query: str, glob_pattern: str = "**/*",
             case_sensitive: bool = False, max_results: int = 1000) -> list[SearchResult]: ...

    # Metadata & Control
    def get_metadata(self, path: str) -> FileMetadata: ...
    def is_ready(self) -> bool: ...
    def is_watching(self) -> bool: ...
    def refresh(self) -> None: ...
    def close(self) -> None: ...
```

### AsyncFileSystem

Same API as `FileSystem`, but all I/O methods are `async`.

### Data Classes

```python
class SearchResult:
    file: str           # Relative file path
    line_number: int    # Line number (1-indexed)
    content: str        # Matching line content

class FileMetadata:
    size: int       # File size in bytes
    mtime: float    # Modification time (Unix timestamp)
    is_dir: bool    # Is directory
    is_binary: bool # Is binary file
```

## Performance

Benchmark on 3000 files (polyglot project, 20 repeated queries):

| Operation | Agent-Gear | Stdlib | Speedup |
|-----------|------------|--------|---------|
| **List all** | 1.75ms | 3.5ms | **2.0x** |
| **Glob *.py** | 1.84ms | 5.1ms | **2.8x** |
| **Glob *.ts** | 2.01ms | 5.0ms | **2.5x** |
| **Grep TODO** | 4.2ms | 7.8ms | **1.9x** |
| **Write (fast)** | 0.14ms | 4.5ms (atomic) | **33x** |
| **Async (3 ops)** | 3.9ms | 8.0ms (seq) | **2.0x** |

**Overall: 1.9x faster** | Index: ~100ms (breaks even in 1 query round)

### When to Use Agent-Gear

- **Repeated queries**: Index pays off after just 1-2 query rounds
- **Large codebases**: 1000+ files show 1.5-3x speedup
- **Glob-heavy workflows**: Cached patterns, 2-3x faster
- **Grep searches**: Parallel + mmap, 2x faster
- **Async I/O**: Concurrent operations with 2x speedup

Run benchmarks:
```bash
python benchmarks/benchmark.py                     # Single mode, 500 files
python benchmarks/benchmark.py --mode repeated     # Repeated queries
python benchmarks/benchmark.py --mode all --files 3000  # Full test
```

## Architecture

```
agent_gear/
├── _rust_core.so      # Rust extension (PyO3)
└── __init__.py        # Python wrapper + AsyncFileSystem

src/
├── lib.rs             # PyO3 module entry
└── fs/
    ├── mod.rs         # FileSystem pyclass
    ├── index.rs       # DashMap-based file index + LRU glob cache
    ├── searcher.rs    # Parallel grep with mmap
    ├── io.rs          # Batch read/write with threshold optimization
    ├── atomic.rs      # Atomic write (temp-fsync-rename)
    └── watcher.rs     # File watching with debouncing
```

## Development

### Prerequisites

- Python 3.12+
- Rust 1.75+
- maturin

### Build & Test

```bash
# Development build
maturin develop --release

# Run tests
pytest tests/python -v
cargo test

# Run benchmarks
cargo bench
python benchmarks/benchmark.py
```

## License

MIT
