"""Tests for external path support in agent_gear.FileSystem."""

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

        # Create files
        (root / "src" / "main.py").write_text(
            '''"""Main module."""

def main():
    """Entry point."""
    print("Hello, World!")
'''
        )

        (root / "README.md").write_text("# Test Project\n\nThis is a test.")

        yield root


@pytest.fixture
def external_dir():
    """Create a temporary external directory (outside project root)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create directory structure
        (root / "external").mkdir()

        # Create files
        (root / "external" / "data.txt").write_text("External data file content.")
        (root / "external" / "config.json").write_text('{"key": "value"}')
        (root / "test.log").write_text("Log line 1\nLog line 2\nLog line 3\n")

        yield root


class TestExternalPathsDisabled:
    """Tests for external path handling when allow_external=False (default)."""

    def test_read_external_file_raises(self, temp_project, external_dir):
        """Test that reading external file raises ValueError."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), allow_external=False)
        fs.wait_ready()

        external_file = str(external_dir / "test.log")

        with pytest.raises(ValueError, match="outside root directory"):
            fs.read_file(external_file)

    def test_write_external_file_raises(self, temp_project, external_dir):
        """Test that writing external file raises ValueError."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), allow_external=False)
        fs.wait_ready()

        external_file = str(external_dir / "new_file.txt")

        with pytest.raises(ValueError, match="outside root directory"):
            fs.write_file(external_file, "content")

    def test_relative_path_still_works(self, temp_project):
        """Test that relative paths work normally."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), allow_external=False)
        fs.wait_ready()

        # Relative path should work
        content = fs.read_file("src/main.py")
        assert "def main():" in content

    def test_absolute_path_within_root_works(self, temp_project):
        """Test that absolute paths within root work."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), allow_external=False)
        fs.wait_ready()

        # Absolute path within root should work
        abs_path = str(temp_project / "src" / "main.py")
        content = fs.read_file(abs_path)
        assert "def main():" in content


class TestExternalPathsEnabled:
    """Tests for external path handling when allow_external=True."""

    def test_read_external_file(self, temp_project, external_dir):
        """Test reading external file."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), allow_external=True)
        fs.wait_ready()

        external_file = str(external_dir / "test.log")
        content = fs.read_file(external_file)

        assert "Log line 1" in content
        assert "Log line 2" in content

    def test_read_lines_external(self, temp_project, external_dir):
        """Test reading lines from external file."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), allow_external=True)
        fs.wait_ready()

        external_file = str(external_dir / "test.log")
        lines = fs.read_lines(external_file, start_line=0, count=2)

        assert len(lines) == 2
        assert lines[0] == "Log line 1"
        assert lines[1] == "Log line 2"

    def test_write_external_file(self, temp_project, external_dir):
        """Test writing to external file."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), allow_external=True)
        fs.wait_ready()

        external_file = str(external_dir / "new_file.txt")
        fs.write_file(external_file, "New content here.")

        # Verify written content
        assert Path(external_file).read_text() == "New content here."

    def test_edit_replace_external(self, temp_project, external_dir):
        """Test editing external file."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), allow_external=True)
        fs.wait_ready()

        external_file = str(external_dir / "test.log")
        result = fs.edit_replace(external_file, "Log line 1", "Modified line 1")

        assert result is True
        content = Path(external_file).read_text()
        assert "Modified line 1" in content
        assert "Log line 1" not in content

    def test_read_batch_mixed_paths(self, temp_project, external_dir):
        """Test reading batch of mixed internal and external paths."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), allow_external=True)
        fs.wait_ready()

        internal_file = "src/main.py"
        external_file = str(external_dir / "test.log")

        results = fs.read_batch([internal_file, external_file])

        # Internal file may be returned with absolute path by Rust
        internal_content = None
        for path, content in results.items():
            if path.endswith("main.py"):
                internal_content = content
                break

        assert internal_content is not None, f"main.py not found in results: {results.keys()}"
        assert external_file in results
        assert "def main():" in internal_content
        assert "Log line 1" in results[external_file]

    def test_list_external_directory(self, temp_project, external_dir):
        """Test listing files in external directory."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), allow_external=True)
        fs.wait_ready()

        # List files in external directory
        pattern = str(external_dir / "external" / "*")
        files = fs.list(pattern)

        # Should find the external files
        assert len(files) >= 2
        file_names = [Path(f).name for f in files]
        assert "data.txt" in file_names
        assert "config.json" in file_names

    def test_grep_external_directory(self, temp_project, external_dir):
        """Test grep in external directory."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), allow_external=True)
        fs.wait_ready()

        # Search in external directory
        pattern = str(external_dir / "**" / "*")
        results = fs.grep("Log line", pattern)

        # Should find matches in external files
        assert len(results) >= 1
        assert any("Log line" in r.content for r in results)

    def test_get_metadata_external(self, temp_project, external_dir):
        """Test getting metadata for external file."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), allow_external=True)
        fs.wait_ready()

        external_file = str(external_dir / "test.log")
        metadata = fs.get_metadata(external_file)

        # Check metadata structure (dict for external paths)
        assert "size" in metadata
        assert "mtime" in metadata
        assert metadata["size"] > 0

    def test_relative_path_still_uses_rust(self, temp_project):
        """Test that relative paths still use Rust implementation."""
        from agent_gear import FileSystem

        fs = FileSystem(str(temp_project), allow_external=True)
        fs.wait_ready()

        # Relative path should work with Rust
        content = fs.read_file("src/main.py")
        assert "def main():" in content


class TestAsyncExternalPaths:
    """Tests for async external path support."""

    def test_async_read_external_file(self, temp_project, external_dir):
        """Test async reading external file."""
        import asyncio

        from agent_gear import AsyncFileSystem

        async def run_test():
            async with AsyncFileSystem(str(temp_project), allow_external=True) as fs:
                await fs.wait_ready()

                external_file = str(external_dir / "test.log")
                content = await fs.read_file(external_file)

                assert "Log line 1" in content

        asyncio.run(run_test())

    def test_async_write_external_file(self, temp_project, external_dir):
        """Test async writing to external file."""
        import asyncio

        from agent_gear import AsyncFileSystem

        async def run_test():
            async with AsyncFileSystem(str(temp_project), allow_external=True) as fs:
                await fs.wait_ready()

                external_file = str(external_dir / "async_new.txt")
                await fs.write_file(external_file, "Async content.")

                assert Path(external_file).read_text() == "Async content."

        asyncio.run(run_test())
