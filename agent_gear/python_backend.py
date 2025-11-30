"""PythonFileBackend: Pure Python file operations for external paths.

This module provides a Python-based file system backend for handling paths
outside the Rust FileSystem's root directory. It uses standard library
functions for all operations.
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path


class PythonFileBackend:
    """Pure Python file system backend for external path operations.

    This class provides file system operations using Python's standard library,
    intended as a fallback for paths outside the Rust FileSystem's root directory.

    All methods accept absolute paths and perform operations directly on the filesystem.
    """

    def __init__(self, max_file_size_mb: int = 10) -> None:
        """Initialize the Python file backend.

        Args:
            max_file_size_mb: Maximum file size in MB for search operations.
        """
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

    def read_file(self, path: str, encoding: str = "utf-8") -> str:
        """Read entire file content.

        Args:
            path: Absolute file path.
            encoding: Text encoding (default: utf-8).

        Returns:
            File content as string.

        Raises:
            FileNotFoundError: If file does not exist.
            IOError: If file cannot be read.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {path}")
        return file_path.read_text(encoding=encoding)

    def read_lines(
        self,
        path: str,
        start_line: int = 0,
        count: int | None = None,
        encoding: str = "utf-8",
    ) -> list[str]:
        """Read specific lines from a file.

        Args:
            path: Absolute file path.
            start_line: Starting line number (0-indexed).
            count: Number of lines to read (None = read to end).
            encoding: Text encoding.

        Returns:
            List of line strings (without trailing newlines).
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        lines: list[str] = []
        with open(file_path, encoding=encoding) as f:
            for i, line in enumerate(f):
                if i < start_line:
                    continue
                if count is not None and len(lines) >= count:
                    break
                lines.append(line.rstrip("\n\r"))
        return lines

    def read_file_range(
        self,
        path: str,
        offset: int,
        limit: int,
        encoding: str = "utf-8",
    ) -> str:
        """Read a byte range from a file.

        Args:
            path: Absolute file path.
            offset: Byte offset to start reading from.
            limit: Maximum bytes to read.
            encoding: Text encoding.

        Returns:
            Content as string.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        with open(file_path, "rb") as f:
            f.seek(offset)
            data = f.read(limit)
        return data.decode(encoding)

    def write_file(self, path: str, content: str, encoding: str = "utf-8") -> bool:
        """Write content to file atomically (using temp file + rename).

        Args:
            path: Absolute file path.
            content: Content to write.
            encoding: Text encoding.

        Returns:
            True if successful.
        """
        file_path = Path(path)

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file first, then rename for atomicity
        temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
        try:
            temp_path.write_text(content, encoding=encoding)
            # fsync to ensure data is on disk
            fd = os.open(str(temp_path), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            # Atomic rename
            temp_path.rename(file_path)
            return True
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def write_file_fast(self, path: str, content: str, encoding: str = "utf-8") -> bool:
        """Write content to file without atomicity guarantee (fast mode).

        Args:
            path: Absolute file path.
            content: Content to write.
            encoding: Text encoding.

        Returns:
            True if successful.
        """
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding=encoding)
        return True

    def edit_replace(
        self,
        path: str,
        old_text: str,
        new_text: str,
        strict: bool = True,
        encoding: str = "utf-8",
    ) -> bool:
        """Replace text in file.

        Args:
            path: Absolute file path.
            old_text: Text to find.
            new_text: Replacement text.
            strict: If true, error if old_text is not unique or not found.
            encoding: Text encoding.

        Returns:
            True if replacement was made.

        Raises:
            ValueError: If strict mode and text not found or not unique.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        content = file_path.read_text(encoding=encoding)
        count = content.count(old_text)

        if count == 0:
            if strict:
                raise ValueError(f"Text not found in file: {path}")
            return False

        if count > 1 and strict:
            raise ValueError(f"Text found {count} times in file (must be unique): {path}")

        new_content = content.replace(old_text, new_text, 1)
        return self.write_file(path, new_content, encoding)

    def list_files(
        self,
        path: str,
        pattern: str = "**/*",
        only_files: bool = True,
    ) -> list[str]:
        """List files matching the given pattern.

        Args:
            path: Base directory path.
            pattern: Glob pattern (default: "**/*").
            only_files: If true, only return files (not directories).

        Returns:
            List of absolute file paths.
        """
        base_path = Path(path)
        if not base_path.exists() or not base_path.is_dir():
            return []

        # Handle pattern
        if pattern.startswith("/"):
            pattern = pattern.lstrip("/")

        results: list[str] = []
        for matched_path in base_path.glob(pattern):
            if only_files and not matched_path.is_file():
                continue
            results.append(str(matched_path))

        results.sort()
        return results

    def glob(self, path: str, pattern: str) -> list[str]:
        """Match files using glob pattern.

        Args:
            path: Base directory path.
            pattern: Glob pattern.

        Returns:
            List of matching absolute file paths.
        """
        return self.list_files(path, pattern, only_files=True)

    def grep(
        self,
        pattern: str,
        path: str,
        glob_pattern: str = "**/*",
        case_sensitive: bool = False,
        max_results: int = 1000,
    ) -> list[dict]:
        """Search files for content matching pattern.

        Args:
            pattern: Regex search pattern.
            path: Base directory to search in.
            glob_pattern: File pattern to search in.
            case_sensitive: Case sensitive search.
            max_results: Maximum number of results.

        Returns:
            List of dicts with 'file', 'line_number', 'content' keys.
        """
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}") from e

        base_path = Path(path)
        if not base_path.exists():
            return []

        results: list[dict] = []
        files = self.list_files(path, glob_pattern, only_files=True)

        for file_path in files:
            if len(results) >= max_results:
                break

            fp = Path(file_path)
            try:
                if fp.stat().st_size > self.max_file_size_bytes:
                    continue
            except OSError:
                continue

            try:
                content = fp.read_text()
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

            for line_num, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    results.append({
                        "file": file_path,
                        "line_number": line_num,
                        "content": line,
                        "context_before": [],
                        "context_after": [],
                    })
                    if len(results) >= max_results:
                        break

        return results

    def get_metadata(self, path: str) -> dict:
        """Get file metadata.

        Args:
            path: Absolute file path.

        Returns:
            Dict with size, mtime, is_dir, is_binary keys.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        stat = file_path.stat()
        is_dir = file_path.is_dir()

        # Simple binary detection: check for null bytes in first 512 bytes
        is_binary = False
        if not is_dir:
            try:
                with open(file_path, "rb") as f:
                    chunk = f.read(512)
                    is_binary = b"\x00" in chunk
            except (OSError, PermissionError):
                pass

        return {
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "is_dir": is_dir,
            "is_binary": is_binary,
        }
