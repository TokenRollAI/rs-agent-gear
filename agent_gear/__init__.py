"""Agent-Gear: High-performance filesystem operations for AI agents.

This package provides a Rust-powered filesystem interface optimized for
AI agent workloads, featuring:

- Stateful in-memory file indexing
- Batch file I/O operations
- High-performance grep search
- File watching with debouncing
- Async/await support
- External path support (Python fallback for paths outside root)

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

External Path Example:
    >>> fs = FileSystem("/path/to/project", allow_external=True)
    >>> # Can now read files outside the project directory
    >>> content = fs.read_file("/tmp/external_file.txt")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from agent_gear._rust_core import (
    FileMetadata,
    SearchOptions,
    SearchResult,
    __version__,
)
from agent_gear._rust_core import FileSystem as _RustFileSystem

if TYPE_CHECKING:
    from agent_gear.python_backend import PythonFileBackend


class _PythonSearchResult:
    """Python-side SearchResult for external path grep results.

    Matches the interface of the Rust SearchResult class.
    """

    def __init__(
        self,
        file: str,
        line_number: int,
        content: str,
        context_before: list[str] | None = None,
        context_after: list[str] | None = None,
    ) -> None:
        self.file = file
        self.line_number = line_number
        self.content = content
        self.context_before = context_before or []
        self.context_after = context_after or []


def _create_search_result(
    file: str,
    line_number: int,
    content: str,
    context_before: list[str] | None = None,
    context_after: list[str] | None = None,
) -> _PythonSearchResult:
    """Create a Python SearchResult object."""
    return _PythonSearchResult(file, line_number, content, context_before, context_after)

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
        allow_external: Whether to allow operations on paths outside root (default: False).
            When True, external paths use a Python fallback implementation.

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

    External Path Example:
        >>> fs = FileSystem("/project", allow_external=True)
        >>> # Read file outside project directory
        >>> content = fs.read_file("/tmp/external.txt")
    """

    _python_backend: PythonFileBackend | None

    def __init__(
        self,
        root: str,
        auto_watch: bool = True,
        allow_external: bool = False,
    ) -> None:
        """Initialize the FileSystem.

        Args:
            root: Root directory path.
            auto_watch: Whether to automatically watch for file changes.
            allow_external: Whether to allow operations on paths outside root.
        """
        self._inner = _RustFileSystem(root, auto_watch)
        self._root = os.path.abspath(root)
        self._allow_external = allow_external
        self._python_backend = None
        if allow_external:
            from agent_gear.python_backend import PythonFileBackend

            self._python_backend = PythonFileBackend()

    def _is_within_root(self, path: str) -> bool:
        """Check if a path is within the root directory.

        Args:
            path: File path (relative or absolute).

        Returns:
            True if path is relative or within root, False otherwise.
        """
        if not os.path.isabs(path):
            return True  # Relative paths are always within root
        abs_path = os.path.abspath(path)
        return abs_path.startswith(self._root + os.sep) or abs_path == self._root

    def _check_external_allowed(self, path: str) -> None:
        """Check if external path access is allowed.

        Raises:
            ValueError: If path is external and allow_external=False.
        """
        if not self._is_within_root(path) and not self._allow_external:
            raise ValueError(
                f"Path '{path}' is outside root directory '{self._root}' "
                "and allow_external=False"
            )

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
        """List files matching the given pattern from memory index.

        Args:
            pattern: Glob pattern (default: "**/*"). Can be absolute path for external dirs.
            only_files: If true, only return files (not directories).

        Returns:
            List of file paths relative to root (or absolute for external).

        Note:
            If pattern starts with "/" and points outside root,
            Python fallback is used for the listing.
        """
        # Check if pattern points to external path
        if pattern.startswith("/"):
            # Extract base directory from pattern
            parts = pattern.split("/")
            base_path = "/" + parts[1] if len(parts) > 1 else "/"
            if not self._is_within_root(base_path):
                self._check_external_allowed(base_path)
                assert self._python_backend is not None
                # Extract pattern after base path
                remaining_pattern = "/".join(parts[2:]) if len(parts) > 2 else "**/*"
                return self._python_backend.list_files(base_path, remaining_pattern, only_files)
        return self._inner.list(pattern, only_files)

    def glob(self, pattern: str) -> list[str]:
        """Match files using glob pattern.

        Args:
            pattern: Glob pattern. Can be absolute path for external dirs.

        Returns:
            List of matching file paths.

        Note:
            If pattern starts with "/" and points outside root,
            Python fallback is used for the matching.
        """
        # Check if pattern points to external path
        if pattern.startswith("/"):
            parts = pattern.split("/")
            base_path = "/" + parts[1] if len(parts) > 1 else "/"
            if not self._is_within_root(base_path):
                self._check_external_allowed(base_path)
                assert self._python_backend is not None
                remaining_pattern = "/".join(parts[2:]) if len(parts) > 2 else "*"
                return self._python_backend.glob(base_path, remaining_pattern)
        return self._inner.glob(pattern)

    def read_file(self, path: str, encoding: str = "utf-8") -> str:
        """Read a single file.

        Args:
            path: File path (relative to root or absolute).
            encoding: Text encoding (default: utf-8).

        Returns:
            File content as string.

        Raises:
            ValueError: If path is external and allow_external=False.
        """
        if self._is_within_root(path):
            return self._inner.read_file(path, encoding)
        self._check_external_allowed(path)
        assert self._python_backend is not None
        return self._python_backend.read_file(path, encoding)

    def read_batch(self, paths: list[str]) -> dict[str, str]:
        """Read multiple files in parallel.

        Args:
            paths: List of file paths.

        Returns:
            Dict mapping path to content.

        Note:
            For mixed internal/external paths, internal paths use Rust,
            external paths use Python. All paths must be allowed.
        """
        # Separate internal and external paths
        internal_paths = []
        external_paths = []
        for p in paths:
            if self._is_within_root(p):
                internal_paths.append(p)
            else:
                self._check_external_allowed(p)
                external_paths.append(p)

        # Read internal paths with Rust
        result = self._inner.read_batch(internal_paths) if internal_paths else {}

        # Read external paths with Python
        if external_paths and self._python_backend:
            for p in external_paths:
                try:
                    result[p] = self._python_backend.read_file(p)
                except Exception as e:
                    # Match Rust behavior: skip failed reads
                    pass

        return result

    def read_lines(self, path: str, start_line: int = 0, count: int | None = None) -> list[str]:
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
        if self._is_within_root(path):
            return self._inner.read_lines(path, start_line, count)
        self._check_external_allowed(path)
        assert self._python_backend is not None
        return self._python_backend.read_lines(path, start_line, count)

    def read_file_range(self, path: str, offset: int, limit: int) -> str:
        """Read a byte range from a file.

        Args:
            path: File path.
            offset: Byte offset to start reading from.
            limit: Maximum bytes to read.

        Returns:
            Content as string.
        """
        if self._is_within_root(path):
            return self._inner.read_file_range(path, offset, limit)
        self._check_external_allowed(path)
        assert self._python_backend is not None
        return self._python_backend.read_file_range(path, offset, limit)

    def write_file(self, path: str, content: str) -> bool:
        """Write content to file atomically.

        Args:
            path: File path.
            content: Content to write.

        Returns:
            True if successful.
        """
        if self._is_within_root(path):
            return self._inner.write_file(path, content)
        self._check_external_allowed(path)
        assert self._python_backend is not None
        return self._python_backend.write_file(path, content)

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
        if self._is_within_root(path):
            return self._inner.write_file_fast(path, content)
        self._check_external_allowed(path)
        assert self._python_backend is not None
        return self._python_backend.write_file_fast(path, content)

    def edit_replace(
        self,
        path: str,
        old_text: str,
        new_text: str,
        strict: bool = True,
    ) -> bool:
        """Replace text in file.

        Args:
            path: File path.
            old_text: Text to find.
            new_text: Replacement text.
            strict: If true, error if old_text is not unique or not found.

        Returns:
            True if replacement was made.
        """
        if self._is_within_root(path):
            return self._inner.edit_replace(path, old_text, new_text, strict)
        self._check_external_allowed(path)
        assert self._python_backend is not None
        return self._python_backend.edit_replace(path, old_text, new_text, strict)

    def grep(
        self,
        query: str,
        glob_pattern: str = "**/*",
        case_sensitive: bool = False,
        max_results: int = 1000,
    ) -> list[SearchResult]:
        """Search files for content matching query.

        Args:
            query: Search pattern (regex).
            glob_pattern: File pattern to search in. Can be absolute path for external dirs.
            case_sensitive: Case sensitive search.
            max_results: Maximum number of results.

        Returns:
            List of SearchResult objects.

        Note:
            If glob_pattern starts with "/" and points outside root,
            Python fallback is used for the search.
        """
        # Check if pattern points to external path
        if glob_pattern.startswith("/"):
            # Extract base directory from pattern
            # e.g., "/tmp/**/*.py" -> "/tmp"
            parts = glob_pattern.split("/")
            base_path = "/" + parts[1] if len(parts) > 1 else "/"
            if not self._is_within_root(base_path):
                self._check_external_allowed(base_path)
                assert self._python_backend is not None
                results = self._python_backend.grep(
                    query, base_path, glob_pattern[len(base_path):].lstrip("/"),
                    case_sensitive, max_results
                )
                # Convert dict results to SearchResult-like objects
                return [
                    _create_search_result(r["file"], r["line_number"], r["content"])
                    for r in results
                ]
        return self._inner.grep(query, glob_pattern, case_sensitive, max_results)

    def get_metadata(self, path: str) -> FileMetadata | dict:
        """Get file metadata.

        Args:
            path: File path.

        Returns:
            FileMetadata object (Rust) or dict (Python fallback).
        """
        if self._is_within_root(path):
            return self._inner.get_metadata(path)
        self._check_external_allowed(path)
        assert self._python_backend is not None
        return self._python_backend.get_metadata(path)

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

    def __enter__(self) -> FileSystem:
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
        allow_external: Whether to allow operations on paths outside root (default: False).

    Example:
        >>> async with AsyncFileSystem("/path/to/project") as fs:
        ...     await fs.wait_ready()
        ...     files = await fs.list("**/*.py")
        ...     results = await fs.grep("TODO", "**/*.py")
        ...     content = await fs.read_file("main.py")

    External Path Example:
        >>> async with AsyncFileSystem("/project", allow_external=True) as fs:
        ...     content = await fs.read_file("/tmp/external.txt")
    """

    def __init__(
        self,
        root: str,
        auto_watch: bool = True,
        allow_external: bool = False,
    ) -> None:
        """Initialize the AsyncFileSystem.

        Args:
            root: Root directory path.
            auto_watch: Whether to automatically watch for file changes.
            allow_external: Whether to allow operations on paths outside root.
        """
        self._sync = FileSystem(root, auto_watch, allow_external)

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

        return await asyncio.to_thread(self._sync.edit_replace, path, old_text, new_text, strict)

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

    async def __aenter__(self) -> AsyncFileSystem:
        return self

    async def __aexit__(self, *args) -> None:
        self.close()
