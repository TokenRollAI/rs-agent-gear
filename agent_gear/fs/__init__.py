"""File system module.

This module re-exports the main FileSystem class and related types
for convenience.
"""

from agent_gear import (
    FileMetadata,
    FileSystem,
    SearchOptions,
    SearchResult,
)

__all__ = [
    "FileSystem",
    "FileMetadata",
    "SearchOptions",
    "SearchResult",
]
