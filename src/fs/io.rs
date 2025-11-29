//! Batch I/O operations
//!
//! Provides high-performance file read/write operations with:
//! - Parallel batch reading using Rayon
//! - Atomic file writing
//! - Text replacement with safety checks

use pyo3::prelude::*;
use rayon::prelude::*;
use std::collections::HashMap;
use std::path::Path;

use crate::utils::error::{AgentGearError, Result};

/// Read a single file as text
///
/// # Arguments
/// * `py` - Python GIL token
/// * `path` - Path to the file
/// * `encoding` - Text encoding (currently only utf-8 is fully supported)
pub fn read_file(py: Python<'_>, path: &Path, _encoding: &str) -> PyResult<String> {
    py.allow_threads(|| {
        std::fs::read_to_string(path).map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                AgentGearError::PathNotFound(path.display().to_string())
            } else {
                AgentGearError::Io(e)
            }
        })
    })
    .map_err(|e| e.into())
}

/// Threshold for switching to parallel read (files below this use serial read)
const PARALLEL_READ_THRESHOLD: usize = 30;

/// Read multiple files in parallel
///
/// Uses Rayon for parallel file I/O, releasing the Python GIL during execution.
/// For small batches (< 30 files), uses serial read to avoid thread pool overhead.
///
/// # Arguments
/// * `py` - Python GIL token
/// * `paths` - Slice of file paths to read
///
/// # Returns
/// HashMap mapping file path strings to their contents
pub fn read_batch(
    py: Python<'_>,
    paths: &[std::path::PathBuf],
) -> PyResult<HashMap<String, String>> {
    let result = py.allow_threads(|| {
        // Use serial read for small batches to avoid Rayon overhead
        if paths.len() < PARALLEL_READ_THRESHOLD {
            read_batch_serial(paths)
        } else {
            read_batch_parallel(paths)
        }
    });
    Ok(result)
}

/// Serial batch read for small file counts
#[inline]
fn read_batch_serial(paths: &[std::path::PathBuf]) -> HashMap<String, String> {
    let mut result = HashMap::with_capacity(paths.len());
    for path in paths {
        match std::fs::read_to_string(path) {
            Ok(content) => {
                result.insert(path.display().to_string(), content);
            }
            Err(e) => {
                tracing::warn!("Failed to read {}: {}", path.display(), e);
            }
        }
    }
    result
}

/// Parallel batch read using Rayon
#[inline]
fn read_batch_parallel(paths: &[std::path::PathBuf]) -> HashMap<String, String> {
    paths
        .par_iter()
        .filter_map(|path| match std::fs::read_to_string(path) {
            Ok(content) => Some((path.display().to_string(), content)),
            Err(e) => {
                tracing::warn!("Failed to read {}: {}", path.display(), e);
                None
            }
        })
        .collect::<HashMap<String, String>>()
}

/// Write content to a file atomically
///
/// Uses the write-to-temp, fsync, rename pattern to ensure atomicity.
///
/// # Arguments
/// * `py` - Python GIL token
/// * `path` - Target file path
/// * `content` - Content to write
pub fn write_file(py: Python<'_>, path: &Path, content: &str) -> PyResult<()> {
    py.allow_threads(|| super::atomic::atomic_write(path, content.as_bytes()))
        .map_err(|e| e.into())
}

/// Write content to a file without atomicity guarantee (fast mode)
///
/// Directly writes content without fsync or rename. Much faster but may
/// result in partial writes on crash.
///
/// # Arguments
/// * `py` - Python GIL token
/// * `path` - Target file path
/// * `content` - Content to write
pub fn write_file_fast(py: Python<'_>, path: &Path, content: &str) -> PyResult<()> {
    use std::io::Write;

    py.allow_threads(|| -> Result<()> {
        // Create parent directories if needed
        if let Some(parent) = path.parent() {
            if !parent.exists() {
                std::fs::create_dir_all(parent)?;
            }
        }

        // Direct write without fsync
        let mut file = std::fs::File::create(path).map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                AgentGearError::PathNotFound(path.display().to_string())
            } else {
                AgentGearError::Io(e)
            }
        })?;

        file.write_all(content.as_bytes())?;

        Ok(())
    })
    .map_err(|e| e.into())
}

/// Replace text in a file
///
/// # Arguments
/// * `py` - Python GIL token
/// * `path` - File path
/// * `old_text` - Text to find
/// * `new_text` - Replacement text
/// * `strict` - If true, error on non-unique or missing match
///
/// # Returns
/// True if replacement was made, false if old_text was not found (when strict=false)
pub fn edit_replace(
    py: Python<'_>,
    path: &Path,
    old_text: &str,
    new_text: &str,
    strict: bool,
) -> PyResult<bool> {
    py.allow_threads(|| -> Result<bool> {
        // Read the file
        let content = std::fs::read_to_string(path).map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                AgentGearError::PathNotFound(path.display().to_string())
            } else {
                AgentGearError::Io(e)
            }
        })?;

        // Count occurrences
        let count = content.matches(old_text).count();

        if count == 0 {
            if strict {
                return Err(AgentGearError::TextNotFound);
            }
            return Ok(false);
        }

        if count > 1 && strict {
            return Err(AgentGearError::TextNotUnique(count));
        }

        // Perform replacement
        let new_content = content.replace(old_text, new_text);

        // Write atomically
        super::atomic::atomic_write(path, new_content.as_bytes())?;

        Ok(true)
    })
    .map_err(|e| e.into())
}

/// Read specific lines from a file (for large files)
///
/// Efficiently reads a range of lines without loading the entire file.
/// Uses memory-mapped I/O for large files and buffered reading for smaller ones.
///
/// # Arguments
/// * `py` - Python GIL token
/// * `path` - File path
/// * `start_line` - Starting line number (0-indexed)
/// * `count` - Number of lines to read (None = read to end)
///
/// # Returns
/// Vector of line strings (without trailing newlines)
pub fn read_lines(
    py: Python<'_>,
    path: &Path,
    start_line: usize,
    count: Option<usize>,
) -> PyResult<Vec<String>> {
    use memmap2::Mmap;
    use std::io::{BufRead, BufReader};

    py.allow_threads(|| -> Result<Vec<String>> {
        let file = std::fs::File::open(path).map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                AgentGearError::PathNotFound(path.display().to_string())
            } else {
                AgentGearError::Io(e)
            }
        })?;

        let metadata = file.metadata()?;
        let file_size = metadata.len() as usize;

        // Use mmap for large files (> 1MB), buffered read for smaller
        let lines: Vec<String> = if file_size > 1024 * 1024 {
            // Memory-mapped approach for large files
            let mmap = unsafe { Mmap::map(&file) }.map_err(AgentGearError::Io)?;
            let content = std::str::from_utf8(&mmap)
                .map_err(|e| AgentGearError::Internal(format!("Invalid UTF-8: {}", e)))?;

            let line_iter = content.lines().skip(start_line);
            match count {
                Some(n) => line_iter.take(n).map(|s| s.to_string()).collect(),
                None => line_iter.map(|s| s.to_string()).collect(),
            }
        } else {
            // Buffered read for smaller files
            let reader = BufReader::new(file);
            let line_iter = reader.lines().skip(start_line).filter_map(|l| l.ok());
            match count {
                Some(n) => line_iter.take(n).collect(),
                None => line_iter.collect(),
            }
        };

        Ok(lines)
    })
    .map_err(|e| e.into())
}

/// Read file with offset and limit (for large files)
///
/// # Arguments
/// * `py` - Python GIL token
/// * `path` - File path
/// * `offset` - Byte offset to start reading from
/// * `limit` - Maximum bytes to read
pub fn read_file_range(py: Python<'_>, path: &Path, offset: u64, limit: usize) -> PyResult<String> {
    use std::io::{Read, Seek, SeekFrom};

    py.allow_threads(|| -> Result<String> {
        let mut file = std::fs::File::open(path).map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                AgentGearError::PathNotFound(path.display().to_string())
            } else {
                AgentGearError::Io(e)
            }
        })?;

        file.seek(SeekFrom::Start(offset))?;

        let mut buffer = vec![0u8; limit];
        let bytes_read = file.read(&mut buffer)?;
        buffer.truncate(bytes_read);

        String::from_utf8(buffer)
            .map_err(|e| AgentGearError::Internal(format!("Invalid UTF-8: {}", e)))
    })
    .map_err(|e| e.into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_read_write() {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let dir = tempdir().unwrap();
            let file_path = dir.path().join("test.txt");

            // Write
            write_file(py, &file_path, "Hello, World!").unwrap();

            // Read
            let content = read_file(py, &file_path, "utf-8").unwrap();
            assert_eq!(content, "Hello, World!");
        });
    }

    #[test]
    fn test_edit_replace() {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let dir = tempdir().unwrap();
            let file_path = dir.path().join("test.txt");

            // Write initial content
            write_file(py, &file_path, "Hello, World!").unwrap();

            // Replace
            let result = edit_replace(py, &file_path, "World", "Rust", true).unwrap();
            assert!(result);

            // Verify
            let content = read_file(py, &file_path, "utf-8").unwrap();
            assert_eq!(content, "Hello, Rust!");
        });
    }

    #[test]
    fn test_edit_replace_not_found() {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let dir = tempdir().unwrap();
            let file_path = dir.path().join("test.txt");

            write_file(py, &file_path, "Hello, World!").unwrap();

            // Should fail in strict mode
            let result = edit_replace(py, &file_path, "NotFound", "Replacement", true);
            assert!(result.is_err());

            // Should return false in non-strict mode
            let result = edit_replace(py, &file_path, "NotFound", "Replacement", false).unwrap();
            assert!(!result);
        });
    }

    #[test]
    fn test_edit_replace_not_unique() {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let dir = tempdir().unwrap();
            let file_path = dir.path().join("test.txt");

            write_file(py, &file_path, "Hello Hello Hello").unwrap();

            // Should fail in strict mode
            let result = edit_replace(py, &file_path, "Hello", "Hi", true);
            assert!(result.is_err());

            // Should succeed in non-strict mode (replaces all)
            let result = edit_replace(py, &file_path, "Hello", "Hi", false).unwrap();
            assert!(result);

            let content = read_file(py, &file_path, "utf-8").unwrap();
            assert_eq!(content, "Hi Hi Hi");
        });
    }
}
