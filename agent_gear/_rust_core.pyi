"""Type stubs for the Rust core module."""

from typing import Optional

__version__: str

class FileMetadata:
    """File metadata stored in the index."""

    size: int
    """File size in bytes."""

    mtime: float
    """Modification time as Unix timestamp."""

    is_dir: bool
    """Whether this is a directory."""

    is_binary: bool
    """Whether this appears to be a binary file."""

class SearchOptions:
    """Search options for grep operations."""

    case_sensitive: bool
    """Case sensitive search."""

    max_results: int
    """Maximum number of results."""

    max_file_size: int
    """Maximum file size to search (bytes)."""

    context_lines: int
    """Number of context lines before/after match."""

    def __init__(
        self,
        case_sensitive: bool = False,
        max_results: int = 1000,
        max_file_size: int = 10485760,
        context_lines: int = 0,
    ) -> None: ...

class SearchResult:
    """A single search result."""

    file: str
    """File path where match was found."""

    line_number: int
    """Line number (1-indexed)."""

    content: str
    """The matching line content."""

    context_before: list[str]
    """Context lines before the match."""

    context_after: list[str]
    """Context lines after the match."""

class FileSystem:
    """High-performance file system interface.

    Provides stateful, concurrent file operations with in-memory indexing.
    """

    def __init__(self, root: str, auto_watch: bool = True) -> None:
        """Create a new FileSystem instance.

        Args:
            root: Root directory path.
            auto_watch: Whether to automatically watch for file changes.
        """
        ...

    def list(self, pattern: str = "**/*", only_files: bool = True) -> list[str]:
        """List files matching the given pattern from memory index.

        Args:
            pattern: Glob pattern (default: "**/*").
            only_files: If true, only return files (not directories).

        Returns:
            List of file paths relative to root.
        """
        ...

    def glob(self, pattern: str) -> list[str]:
        """Match files using glob pattern.

        Args:
            pattern: Glob pattern.

        Returns:
            List of matching file paths.
        """
        ...

    def read_file(self, path: str, encoding: str = "utf-8") -> str:
        """Read a single file.

        Args:
            path: File path (relative to root or absolute).
            encoding: Text encoding (default: "utf-8").

        Returns:
            File content as string.
        """
        ...

    def read_batch(self, paths: list[str]) -> dict[str, str]:
        """Read multiple files in parallel.

        Args:
            paths: List of file paths.

        Returns:
            Dict mapping path to content.
        """
        ...

    def read_lines(
        self,
        path: str,
        start_line: int = 0,
        count: Optional[int] = None,
    ) -> list[str]:
        """Read specific lines from a file (for large files).

        Args:
            path: File path.
            start_line: Starting line number (0-indexed).
            count: Number of lines to read (None = read to end).

        Returns:
            List of line strings (without trailing newlines).
        """
        ...

    def read_file_range(
        self,
        path: str,
        offset: int,
        limit: int,
    ) -> str:
        """Read a byte range from a file.

        Args:
            path: File path.
            offset: Byte offset to start reading from.
            limit: Maximum bytes to read.

        Returns:
            Content as string.
        """
        ...

    def write_file(self, path: str, content: str) -> bool:
        """Write content to file atomically.

        Args:
            path: File path.
            content: Content to write.

        Returns:
            True if successful.
        """
        ...

    def write_file_fast(self, path: str, content: str) -> bool:
        """Write content to file without atomicity guarantee (fast mode).

        Args:
            path: File path.
            content: Content to write.

        Returns:
            True if successful.
        """
        ...

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
        ...

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
            glob_pattern: File pattern to search in.
            case_sensitive: Case sensitive search.
            max_results: Maximum number of results.

        Returns:
            List of SearchResult objects.
        """
        ...

    def get_metadata(self, path: str) -> FileMetadata:
        """Get file metadata.

        Args:
            path: File path.

        Returns:
            FileMetadata object.
        """
        ...

    def refresh(self) -> None:
        """Force refresh the file index."""
        ...

    def is_ready(self) -> bool:
        """Check if the index is ready."""
        ...

    def is_watching(self) -> bool:
        """Check if file watching is active."""
        ...

    def pending_changes(self) -> int:
        """Get the number of pending file change events."""
        ...

    def close(self) -> None:
        """Close the filesystem and release resources."""
        ...

    def __enter__(self) -> "FileSystem": ...
    def __exit__(
        self,
        exc_type: Optional[type],
        exc_value: Optional[BaseException],
        traceback: Optional[object],
    ) -> bool: ...
