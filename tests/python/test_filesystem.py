"""Integration tests for agent_gear.FileSystem."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_project():
    """Create a temporary project directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create directory structure
        (root / "src").mkdir()
        (root / "tests").mkdir()

        # Create files
        (root / "src" / "main.py").write_text(
            '''"""Main module."""

def main():
    """Entry point."""
    print("Hello, World!")

if __name__ == "__main__":
    main()
'''
        )

        (root / "src" / "utils.py").write_text(
            '''"""Utility functions."""

def helper():
    """A helper function."""
    return 42

def another_helper():
    """Another helper."""
    return "hello"
'''
        )

        (root / "tests" / "test_main.py").write_text(
            '''"""Tests for main module."""

def test_main():
    """Test main function."""
    assert True
'''
        )

        (root / "README.md").write_text("# Test Project\n\nThis is a test.")

        yield root


class TestFileSystem:
    """Tests for FileSystem class."""

    def test_init(self, temp_project):
        """Test FileSystem initialization."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))
        assert fs.wait_ready(timeout=5.0)

    def test_list_all_files(self, temp_project):
        """Test listing all files."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))
        fs.wait_ready()

        files = fs.list("**/*")
        assert len(files) == 4  # main.py, utils.py, test_main.py, README.md

    def test_glob_pattern(self, temp_project):
        """Test glob pattern matching."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))
        fs.wait_ready()

        py_files = fs.glob("**/*.py")
        assert len(py_files) == 3

        src_files = fs.glob("src/*.py")
        assert len(src_files) == 2

    def test_read_file(self, temp_project):
        """Test reading a single file."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))
        content = fs.read_file("src/main.py")
        assert "def main():" in content
        assert "Hello, World!" in content

    def test_read_batch(self, temp_project):
        """Test batch file reading."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))
        fs.wait_ready()

        paths = ["src/main.py", "src/utils.py"]
        contents = fs.read_batch(paths)

        assert len(contents) == 2
        assert "def main():" in contents[str(temp_project / "src/main.py")]
        assert "def helper():" in contents[str(temp_project / "src/utils.py")]

    def test_write_file(self, temp_project):
        """Test writing a file."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))

        # Write new file
        fs.write_file("new_file.txt", "Hello, Test!")

        # Read it back
        content = fs.read_file("new_file.txt")
        assert content == "Hello, Test!"

    def test_edit_replace(self, temp_project):
        """Test text replacement."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))

        # Replace text
        result = fs.edit_replace("README.md", "Test Project", "My Project")
        assert result is True

        # Verify
        content = fs.read_file("README.md")
        assert "My Project" in content
        assert "Test Project" not in content

    def test_edit_replace_strict_not_found(self, temp_project):
        """Test edit_replace fails in strict mode when text not found."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))

        with pytest.raises(ValueError, match="not found"):
            fs.edit_replace("README.md", "NonExistent", "Replacement", strict=True)

    def test_grep_basic(self, temp_project):
        """Test basic grep search."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))
        fs.wait_ready()

        results = fs.grep("def", "**/*.py")
        assert len(results) >= 3  # main, helper, another_helper, test_main

    def test_grep_glob_filter(self, temp_project):
        """Test grep with glob filter."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))
        fs.wait_ready()

        # Only search in src/
        results = fs.grep("def", "src/*.py")
        for r in results:
            assert r.file.startswith("src/")

    def test_grep_case_sensitive(self, temp_project):
        """Test case-sensitive grep."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))
        fs.wait_ready()

        # Case insensitive (default)
        results = fs.grep("hello", "**/*", case_sensitive=False)
        assert len(results) >= 1

        # Case sensitive
        results = fs.grep("hello", "**/*", case_sensitive=True)
        # Should only match lowercase "hello" in utils.py
        hello_results = [r for r in results if "hello" in r.content.lower()]
        assert all("hello" in r.content for r in hello_results)

    def test_grep_max_results(self, temp_project):
        """Test grep result limiting."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))
        fs.wait_ready()

        results = fs.grep("def", "**/*", max_results=1)
        assert len(results) == 1

    def test_context_manager(self, temp_project):
        """Test using FileSystem as context manager."""
        from agent_gear import FileSystem

        with FileSystem(str(temp_project)) as fs:
            fs.wait_ready()
            files = fs.list("**/*")
            assert len(files) > 0

    def test_get_metadata(self, temp_project):
        """Test getting file metadata."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))
        fs.wait_ready()

        metadata = fs.get_metadata("src/main.py")
        assert metadata.size > 0
        assert not metadata.is_dir
        assert not metadata.is_binary


class TestSearchResult:
    """Tests for SearchResult class."""

    def test_search_result_attributes(self, temp_project):
        """Test SearchResult attributes."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project))
        fs.wait_ready()

        results = fs.grep("main", "**/*.py")
        assert len(results) > 0

        result = results[0]
        assert hasattr(result, "file")
        assert hasattr(result, "line_number")
        assert hasattr(result, "content")
        assert hasattr(result, "context_before")
        assert hasattr(result, "context_after")

        assert isinstance(result.line_number, int)
        assert result.line_number > 0


class TestFileWatching:
    """Tests for file watching functionality."""

    def test_is_watching_enabled(self, temp_project):
        """Test that file watching is enabled by default."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), auto_watch=True)
        # Watching should be active
        assert fs.is_watching()
        fs.close()

    def test_is_watching_disabled(self, temp_project):
        """Test that file watching can be disabled."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), auto_watch=False)
        # Watching should not be active
        assert not fs.is_watching()
        fs.close()

    def test_file_creation_detected(self, temp_project):
        """Test that new files are detected by the watcher."""
        import time
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), auto_watch=True)
        fs.wait_ready()

        initial_count = len(fs.list("**/*"))

        # Create a new file
        new_file = temp_project / "new_watched_file.py"
        new_file.write_text("# New file\n")

        # Wait for watcher to detect the change
        time.sleep(0.5)

        # Refresh to apply any pending changes
        # (In production, this would happen automatically via the watcher thread)
        fs.refresh()

        new_count = len(fs.list("**/*"))
        assert new_count > initial_count, "New file should be detected"

        fs.close()

    def test_file_deletion_detected(self, temp_project):
        """Test that deleted files are detected by the watcher."""
        import time
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), auto_watch=True)
        fs.wait_ready()

        initial_count = len(fs.list("**/*"))

        # Delete a file
        file_to_delete = temp_project / "README.md"
        file_to_delete.unlink()

        # Wait for watcher to detect the change
        time.sleep(0.5)

        # Refresh to apply any pending changes
        fs.refresh()

        new_count = len(fs.list("**/*"))
        assert new_count < initial_count, "Deleted file should be removed from index"

        fs.close()

    def test_close_stops_watching(self, temp_project):
        """Test that close() stops the file watcher."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), auto_watch=True)
        assert fs.is_watching()

        fs.close()
        assert not fs.is_watching()
