//! File system module
//!
//! This module provides high-performance file system operations:
//! - `io`: Batch read/write operations
//! - `index`: In-memory file indexing
//! - `searcher`: Grep-like search engine
//! - `atomic`: Atomic file write operations
//! - `watcher`: File system watching with debouncing

pub mod atomic;
pub mod index;
pub mod io;
pub mod searcher;
pub mod watcher;

use pyo3::prelude::*;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use crate::utils::error::AgentGearError;
use index::FileIndex;
use searcher::{SearchOptions, SearchResult, Searcher};
use watcher::{ChangeKind, FileWatcher};

/// High-performance file system interface
///
/// Provides stateful, concurrent file operations with in-memory indexing.
#[pyclass]
pub struct FileSystem {
    root: PathBuf,
    index: Arc<FileIndex>,
    searcher: Searcher,
    watcher: Option<Arc<FileWatcher>>,
    watcher_thread: Option<std::thread::JoinHandle<()>>,
    stop_flag: Arc<AtomicBool>,
}

#[pymethods]
impl FileSystem {
    /// Create a new FileSystem instance
    ///
    /// Args:
    ///     root: Root directory path
    ///     auto_watch: Whether to automatically watch for file changes
    #[new]
    #[pyo3(signature = (root, auto_watch = true))]
    pub fn new(root: String, auto_watch: bool) -> PyResult<Self> {
        let root_path = PathBuf::from(&root);

        if !root_path.exists() {
            return Err(AgentGearError::PathNotFound(root).into());
        }

        if !root_path.is_dir() {
            return Err(
                AgentGearError::PathNotFound(format!("{} is not a directory", root)).into(),
            );
        }

        let index = Arc::new(FileIndex::new(root_path.clone()));
        let searcher = Searcher::new(root_path.clone());
        let stop_flag = Arc::new(AtomicBool::new(false));

        // Start background indexing
        let index_clone = Arc::clone(&index);
        std::thread::spawn(move || {
            if let Err(e) = index_clone.build() {
                tracing::error!("Failed to build index: {}", e);
            }
        });

        // Optionally start file watcher
        let (watcher, watcher_thread) = if auto_watch {
            match FileWatcher::new(root_path.clone(), Duration::from_millis(100)) {
                Ok(w) => {
                    let watcher = Arc::new(w);
                    let watcher_clone = Arc::clone(&watcher);
                    let index_clone = Arc::clone(&index);
                    let stop_flag_clone = Arc::clone(&stop_flag);

                    let handle = std::thread::spawn(move || {
                        Self::watcher_loop(watcher_clone, index_clone, stop_flag_clone);
                    });

                    (Some(watcher), Some(handle))
                }
                Err(e) => {
                    tracing::warn!("Failed to start file watcher: {}", e);
                    (None, None)
                }
            }
        } else {
            (None, None)
        };

        Ok(Self {
            root: root_path,
            index,
            searcher,
            watcher,
            watcher_thread,
            stop_flag,
        })
    }

    /// List files matching the given pattern from memory index
    ///
    /// Args:
    ///     pattern: Glob pattern (default: "**/*")
    ///     only_files: If true, only return files (not directories)
    ///
    /// Returns:
    ///     List of file paths relative to root
    #[pyo3(signature = (pattern = "**/*", only_files = true))]
    pub fn list(&self, pattern: &str, only_files: bool) -> PyResult<Vec<String>> {
        self.index.list(pattern, only_files).map_err(|e| e.into())
    }

    /// Match files using glob pattern
    ///
    /// Args:
    ///     pattern: Glob pattern
    ///
    /// Returns:
    ///     List of matching file paths
    pub fn glob(&self, pattern: &str) -> PyResult<Vec<String>> {
        self.index.glob(pattern).map_err(|e| e.into())
    }

    /// Read a single file
    ///
    /// Args:
    ///     path: File path (relative to root or absolute)
    ///     encoding: Text encoding (default: "utf-8")
    ///
    /// Returns:
    ///     File content as string
    #[pyo3(signature = (path, encoding = "utf-8"))]
    pub fn read_file(&self, py: Python<'_>, path: &str, encoding: &str) -> PyResult<String> {
        let full_path = self.resolve_path(path);
        io::read_file(py, &full_path, encoding)
    }

    /// Read multiple files in parallel
    ///
    /// Args:
    ///     paths: List of file paths
    ///
    /// Returns:
    ///     Dict mapping path to content
    pub fn read_batch(
        &self,
        py: Python<'_>,
        paths: Vec<String>,
    ) -> PyResult<std::collections::HashMap<String, String>> {
        let full_paths: Vec<PathBuf> = paths.iter().map(|p| self.resolve_path(p)).collect();
        io::read_batch(py, &full_paths)
    }

    /// Read specific lines from a file (for large files)
    ///
    /// Efficiently reads a range of lines without loading the entire file.
    /// Uses memory-mapped I/O for large files (> 1MB).
    ///
    /// Args:
    ///     path: File path
    ///     start_line: Starting line number (0-indexed)
    ///     count: Number of lines to read (None = read to end)
    ///
    /// Returns:
    ///     List of line strings (without trailing newlines)
    #[pyo3(signature = (path, start_line = 0, count = None))]
    pub fn read_lines(
        &self,
        py: Python<'_>,
        path: &str,
        start_line: usize,
        count: Option<usize>,
    ) -> PyResult<Vec<String>> {
        let full_path = self.resolve_path(path);
        io::read_lines(py, &full_path, start_line, count)
    }

    /// Read a byte range from a file
    ///
    /// Args:
    ///     path: File path
    ///     offset: Byte offset to start reading from
    ///     limit: Maximum bytes to read
    ///
    /// Returns:
    ///     Content as string
    #[pyo3(signature = (path, offset, limit))]
    pub fn read_file_range(
        &self,
        py: Python<'_>,
        path: &str,
        offset: u64,
        limit: usize,
    ) -> PyResult<String> {
        let full_path = self.resolve_path(path);
        io::read_file_range(py, &full_path, offset, limit)
    }

    /// Write content to file atomically
    ///
    /// Args:
    ///     path: File path
    ///     content: Content to write
    ///
    /// Returns:
    ///     True if successful
    pub fn write_file(&self, py: Python<'_>, path: &str, content: &str) -> PyResult<bool> {
        let full_path = self.resolve_path(path);
        io::write_file(py, &full_path, content)?;
        Ok(true)
    }

    /// Write content to file without atomicity guarantee (fast mode)
    ///
    /// Much faster than write_file() but does not guarantee data integrity
    /// on crash. Use for temporary files or when speed is critical.
    ///
    /// Warning:
    ///     This operation is not atomic. Also, index updates rely on the
    ///     asynchronous file watcher, so `list()` might not immediately
    ///     reflect the new file.
    ///
    /// Args:
    ///     path: File path
    ///     content: Content to write
    ///
    /// Returns:
    ///     True if successful
    pub fn write_file_fast(&self, py: Python<'_>, path: &str, content: &str) -> PyResult<bool> {
        let full_path = self.resolve_path(path);
        io::write_file_fast(py, &full_path, content)?;
        Ok(true)
    }

    /// Replace text in file
    ///
    /// Args:
    ///     path: File path
    ///     old_text: Text to find
    ///     new_text: Replacement text
    ///     strict: If true, error if old_text is not unique or not found
    ///
    /// Warning:
    ///     This operation is NOT atomic across processes. It performs a
    ///     read-modify-write cycle. If multiple processes modify the file
    ///     concurrently, changes may be lost.
    ///
    /// Returns:
    ///     True if replacement was made
    #[pyo3(signature = (path, old_text, new_text, strict = true))]
    pub fn edit_replace(
        &self,
        py: Python<'_>,
        path: &str,
        old_text: &str,
        new_text: &str,
        strict: bool,
    ) -> PyResult<bool> {
        let full_path = self.resolve_path(path);
        io::edit_replace(py, &full_path, old_text, new_text, strict)
    }

    /// Search files for content matching query
    ///
    /// Args:
    ///     query: Search pattern (regex)
    ///     glob_pattern: File pattern to search in
    ///     case_sensitive: Case sensitive search
    ///     max_results: Maximum number of results
    ///
    /// Returns:
    ///     List of SearchResult objects
    #[pyo3(signature = (query, glob_pattern = "**/*", case_sensitive = false, max_results = 1000))]
    pub fn grep(
        &self,
        py: Python<'_>,
        query: &str,
        glob_pattern: &str,
        case_sensitive: bool,
        max_results: usize,
    ) -> PyResult<Vec<SearchResult>> {
        let options = SearchOptions {
            case_sensitive,
            max_results,
            max_file_size: 10 * 1024 * 1024, // 10MB
            context_lines: 0,
        };

        // Use index if ready, otherwise fall back to directory scan
        if self.index.is_ready() {
            match self.index.glob_paths(glob_pattern) {
                Ok(files) => {
                    return self.searcher.grep_with_files(py, query, files, &options);
                }
                Err(_) => {
                    // Fall back to standard grep
                }
            }
        }

        self.searcher.grep(py, query, glob_pattern, &options)
    }

    /// Get file metadata
    ///
    /// Args:
    ///     path: File path
    ///
    /// Returns:
    ///     FileMetadata object
    pub fn get_metadata(&self, path: &str) -> PyResult<index::FileMetadata> {
        let full_path = self.resolve_path(path);
        self.index
            .get_metadata(&full_path)
            .ok_or_else(|| AgentGearError::PathNotFound(path.to_string()).into())
    }

    /// Force refresh the file index
    pub fn refresh(&self) -> PyResult<()> {
        self.index.refresh().map_err(|e| e.into())
    }

    /// Check if the index is ready
    pub fn is_ready(&self) -> bool {
        self.index.is_ready()
    }

    /// Close the filesystem and release resources
    pub fn close(&self) {
        // Signal the watcher thread to stop
        self.stop_flag.store(true, Ordering::SeqCst);

        // Stop the watcher
        if let Some(ref watcher) = self.watcher {
            watcher.stop();
        }
    }

    /// Check if file watching is active
    pub fn is_watching(&self) -> bool {
        self.watcher.is_some() && !self.stop_flag.load(Ordering::SeqCst)
    }

    /// Get the number of pending file change events
    pub fn pending_changes(&self) -> usize {
        if let Some(ref watcher) = self.watcher {
            // Process events and return count
            let events = watcher.process_events();
            events.len()
        } else {
            0
        }
    }

    fn __enter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    #[pyo3(signature = (_exc_type=None, _exc_value=None, _traceback=None))]
    fn __exit__(
        &self,
        _exc_type: Option<&Bound<'_, PyAny>>,
        _exc_value: Option<&Bound<'_, PyAny>>,
        _traceback: Option<&Bound<'_, PyAny>>,
    ) -> bool {
        self.close();
        false
    }
}

impl FileSystem {
    /// Resolve a path relative to the root directory
    fn resolve_path(&self, path: &str) -> PathBuf {
        let path = PathBuf::from(path);
        if path.is_absolute() {
            path
        } else {
            self.root.join(path)
        }
    }

    /// Background watcher loop that processes file changes and updates the index
    fn watcher_loop(watcher: Arc<FileWatcher>, index: Arc<FileIndex>, stop_flag: Arc<AtomicBool>) {
        loop {
            // Check if we should stop
            if stop_flag.load(Ordering::SeqCst) {
                break;
            }

            // Process pending events
            let events = watcher.process_events();

            for event in events {
                match event.kind {
                    ChangeKind::Created => {
                        // Add to index
                        if let Err(e) = index.add_path(&event.path) {
                            tracing::warn!("Failed to add path to index: {}", e);
                        }
                    }
                    ChangeKind::Modified => {
                        // Update metadata in index
                        if let Err(e) = index.update_path(&event.path) {
                            tracing::warn!("Failed to update path in index: {}", e);
                        }
                    }
                    ChangeKind::Deleted => {
                        // Remove from index
                        index.remove_path(&event.path);
                    }
                    ChangeKind::Renamed { from, to } => {
                        // Remove old path and add new path
                        index.remove_path(&from);
                        if let Err(e) = index.add_path(&to) {
                            tracing::warn!("Failed to add renamed path to index: {}", e);
                        }
                    }
                }
            }

            // Sleep briefly to avoid busy waiting
            std::thread::sleep(Duration::from_millis(50));
        }
    }
}
