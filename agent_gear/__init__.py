"""Agent-Gear: High-performance filesystem operations for AI agents.

This package provides a Rust-powered filesystem interface optimized for
AI agent workloads, featuring:

- Stateful in-memory file indexing
- Batch file I/O operations
- High-performance grep search
- File watching with debouncing
- Async/await support

Example:
    >>> from agent_gear import FileSystem
    >>> fs = FileSystem("/path/to/project")
    >>> files = fs.list("**/*.py")
    >>> results = fs.grep("def main", "**/*.py")

Async Example:
    >>> from agent_gear import AsyncFileSystem
    >>> async with AsyncFileSystem("/path/to/project") as fs:
    ...     files = await fs.list("**/*.py")
    ...     results = await fs.grep("TODO", "**/*.py")
"""

from agent_gear._rust_core import (
    FileMetadata,
    SearchOptions,
    SearchResult,
    __version__,
)
from agent_gear._rust_core import FileSystem as _RustFileSystem

__all__ = [
    "FileSystem",
    "AsyncFileSystem",
    "FileMetadata",
    "SearchOptions",
    "SearchResult",
    "__version__",
]


class FileSystem:
    """High-performance file system interface.

    Provides stateful, concurrent file operations with in-memory indexing.

    Args:
        root: Root directory path to operate on.
        auto_watch: Whether to automatically watch for file changes (default: True).

    Example:
        >>> with FileSystem("/path/to/project") as fs:
        ...     # List all Python files
        ...     py_files = fs.list("**/*.py")
        ...
        ...     # Search for a pattern
        ...     results = fs.grep("TODO", "**/*.py")
        ...
        ...     # Read multiple files at once
        ...     contents = fs.read_batch(py_files[:10])
    """

    def __init__(self, root: str, auto_watch: bool = True) -> None:
        """Initialize the FileSystem.

        Args:
            root: Root directory path.
            auto_watch: Whether to automatically watch for file changes.
        """
        self._inner = _RustFileSystem(root, auto_watch)

    def wait_ready(self, timeout: float = 30.0) -> bool:
        """Wait for the index to be ready.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            True if index is ready, False if timeout was reached.
        """
        import time

        start = time.time()
        while not self.is_ready():
            if time.time() - start > timeout:
                return False
            time.sleep(0.1)
        return True

    def list(self, pattern: str = "**/*", only_files: bool = True) -> list[str]:
        """List files matching the given pattern from memory index."""
        return self._inner.list(pattern, only_files)

    def glob(self, pattern: str) -> list[str]:
        """Match files using glob pattern."""
        return self._inner.glob(pattern)

    def read_file(self, path: str, encoding: str = "utf-8") -> str:
        """Read a single file."""
        return self._inner.read_file(path, encoding)

    def read_batch(self, paths: list[str]) -> dict[str, str]:
        """Read multiple files in parallel."""
        return self._inner.read_batch(paths)

    def read_lines(
        self, path: str, start_line: int = 0, count: int | None = None
    ) -> list[str]:
        """Read specific lines from a file (for large files).

        Efficiently reads a range of lines without loading the entire file.
        Uses memory-mapped I/O for large files (> 1MB).

        Args:
            path: File path.
            start_line: Starting line number (0-indexed).
            count: Number of lines to read (None = read to end).

        Returns:
            List of line strings (without trailing newlines).

        Example:
            >>> # Read first 100 lines
            >>> lines = fs.read_lines("large_log.txt", 0, 100)
            >>> # Read lines 1000-1100
            >>> lines = fs.read_lines("large_log.txt", 1000, 100)
        """
        return self._inner.read_lines(path, start_line, count)

    def read_file_range(self, path: str, offset: int, limit: int) -> str:
        """Read a byte range from a file.

        Args:
            path: File path.
            offset: Byte offset to start reading from.
            limit: Maximum bytes to read.

        Returns:
            Content as string.
        """
        return self._inner.read_file_range(path, offset, limit)

    def write_file(self, path: str, content: str) -> bool:
        """Write content to file atomically."""
        return self._inner.write_file(path, content)

    def write_file_fast(self, path: str, content: str) -> bool:
        """Write content to file without atomicity guarantee (fast mode).

        Much faster than write_file() but does not guarantee data integrity
        on crash. Use for temporary files or when speed is critical.

        Args:
            path: File path.
            content: Content to write.

        Returns:
            True if successful.
        """
        return self._inner.write_file_fast(path, content)

    def edit_replace(
        self,
        path: str,
        old_text: str,
        new_text: str,
        strict: bool = True,
    ) -> bool:
        """Replace text in file."""
        return self._inner.edit_replace(path, old_text, new_text, strict)

    def grep(
        self,
        query: str,
        glob_pattern: str = "**/*",
        case_sensitive: bool = False,
        max_results: int = 1000,
    ) -> list[SearchResult]:
        """Search files for content matching query."""
        return self._inner.grep(query, glob_pattern, case_sensitive, max_results)

    def get_metadata(self, path: str) -> FileMetadata:
        """Get file metadata."""
        return self._inner.get_metadata(path)

    def refresh(self) -> None:
        """Force refresh the file index."""
        self._inner.refresh()

    def is_ready(self) -> bool:
        """Check if the index is ready."""
        return self._inner.is_ready()

    def is_watching(self) -> bool:
        """Check if file watching is active."""
        return self._inner.is_watching()

    def close(self) -> None:
        """Close the filesystem and release resources."""
        self._inner.close()

    def __enter__(self) -> "FileSystem":
        return self

    def __exit__(self, *args) -> None:
        self.close()


class AsyncFileSystem:
    """Async wrapper for FileSystem using asyncio.

    Provides async/await API by running blocking operations in a thread pool.
    All methods that perform I/O are async.

    Args:
        root: Root directory path to operate on.
        auto_watch: Whether to automatically watch for file changes (default: True).

    Example:
        >>> async with AsyncFileSystem("/path/to/project") as fs:
        ...     await fs.wait_ready()
        ...     files = await fs.list("**/*.py")
        ...     results = await fs.grep("TODO", "**/*.py")
        ...     content = await fs.read_file("main.py")
    """

    def __init__(self, root: str, auto_watch: bool = True) -> None:
        """Initialize the AsyncFileSystem.

        Args:
            root: Root directory path.
            auto_watch: Whether to automatically watch for file changes.
        """
        self._sync = FileSystem(root, auto_watch)

    async def wait_ready(self, timeout: float = 30.0) -> bool:
        """Wait for the index to be ready (async).

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            True if index is ready, False if timeout was reached.
        """
        import asyncio

        return await asyncio.to_thread(self._sync.wait_ready, timeout)

    async def list(self, pattern: str = "**/*", only_files: bool = True) -> list[str]:
        """List files matching the given pattern from memory index (async)."""
        import asyncio

        return await asyncio.to_thread(self._sync.list, pattern, only_files)

    async def glob(self, pattern: str) -> list[str]:
        """Match files using glob pattern (async)."""
        import asyncio

        return await asyncio.to_thread(self._sync.glob, pattern)

    async def read_file(self, path: str, encoding: str = "utf-8") -> str:
        """Read a single file (async)."""
        import asyncio

        return await asyncio.to_thread(self._sync.read_file, path, encoding)

    async def read_batch(self, paths: list[str]) -> dict[str, str]:
        """Read multiple files in parallel (async)."""
        import asyncio

        return await asyncio.to_thread(self._sync.read_batch, paths)

    async def read_lines(
        self, path: str, start_line: int = 0, count: int | None = None
    ) -> list[str]:
        """Read specific lines from a file (async).

        Args:
            path: File path.
            start_line: Starting line number (0-indexed).
            count: Number of lines to read (None = read to end).

        Returns:
            List of line strings (without trailing newlines).
        """
        import asyncio

        return await asyncio.to_thread(self._sync.read_lines, path, start_line, count)

    async def read_file_range(self, path: str, offset: int, limit: int) -> str:
        """Read a byte range from a file (async)."""
        import asyncio

        return await asyncio.to_thread(self._sync.read_file_range, path, offset, limit)

    async def write_file(self, path: str, content: str) -> bool:
        """Write content to file atomically (async)."""
        import asyncio

        return await asyncio.to_thread(self._sync.write_file, path, content)

    async def write_file_fast(self, path: str, content: str) -> bool:
        """Write content to file without atomicity guarantee (async)."""
        import asyncio

        return await asyncio.to_thread(self._sync.write_file_fast, path, content)

    async def edit_replace(
        self,
        path: str,
        old_text: str,
        new_text: str,
        strict: bool = True,
    ) -> bool:
        """Replace text in file (async)."""
        import asyncio

        return await asyncio.to_thread(
            self._sync.edit_replace, path, old_text, new_text, strict
        )

    async def grep(
        self,
        query: str,
        glob_pattern: str = "**/*",
        case_sensitive: bool = False,
        max_results: int = 1000,
    ) -> list[SearchResult]:
        """Search files for content matching query (async)."""
        import asyncio

        return await asyncio.to_thread(
            self._sync.grep, query, glob_pattern, case_sensitive, max_results
        )

    async def get_metadata(self, path: str) -> FileMetadata:
        """Get file metadata (async)."""
        import asyncio

        return await asyncio.to_thread(self._sync.get_metadata, path)

    async def refresh(self) -> None:
        """Force refresh the file index (async)."""
        import asyncio

        return await asyncio.to_thread(self._sync.refresh)

    def is_ready(self) -> bool:
        """Check if the index is ready (sync - non-blocking)."""
        return self._sync.is_ready()

    def is_watching(self) -> bool:
        """Check if file watching is active (sync - non-blocking)."""
        return self._sync.is_watching()

    def close(self) -> None:
        """Close the filesystem and release resources."""
        self._sync.close()

    async def __aenter__(self) -> "AsyncFileSystem":
        return self

    async def __aexit__(self, *args) -> None:
        self.close()
