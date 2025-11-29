//! In-memory file index
//!
//! Provides fast file listing and glob matching by maintaining an in-memory
//! representation of the file system structure.

use dashmap::DashMap;
use globset::{Glob, GlobMatcher};
use pyo3::prelude::*;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::RwLock;
use std::time::SystemTime;

use crate::utils::error::{AgentGearError, Result};

/// Maximum number of cached glob patterns
const GLOB_CACHE_SIZE: usize = 128;

/// Threshold for using parallel iteration (below this, serial is faster)
const PARALLEL_ITER_THRESHOLD: usize = 500;

/// File metadata stored in the index
#[pyclass]
#[derive(Clone, Debug)]
pub struct FileMetadata {
    /// File size in bytes
    #[pyo3(get)]
    pub size: u64,

    /// Modification time as Unix timestamp
    #[pyo3(get)]
    pub mtime: f64,

    /// Whether this is a directory
    #[pyo3(get)]
    pub is_dir: bool,

    /// Whether this appears to be a binary file
    #[pyo3(get)]
    pub is_binary: bool,
}

#[pymethods]
impl FileMetadata {
    fn __repr__(&self) -> String {
        format!(
            "FileMetadata(size={}, is_dir={}, is_binary={})",
            self.size, self.is_dir, self.is_binary
        )
    }
}

/// Lock-free glob cache using DashMap
struct GlobCache {
    cache: DashMap<String, GlobMatcher>,
    capacity: usize,
}

impl GlobCache {
    fn new(capacity: usize) -> Self {
        Self {
            cache: DashMap::with_capacity(capacity),
            capacity,
        }
    }

    /// Get a cached matcher (lock-free read)
    #[inline]
    fn get(&self, pattern: &str) -> Option<GlobMatcher> {
        self.cache.get(pattern).map(|r| r.clone())
    }

    /// Insert a matcher, evicting random entry if at capacity
    fn insert(&self, pattern: String, matcher: GlobMatcher) {
        // Simple capacity control: remove one random entry if full
        if self.cache.len() >= self.capacity {
            if let Some(entry) = self.cache.iter().next() {
                let key = entry.key().clone();
                drop(entry);
                self.cache.remove(&key);
            }
        }
        self.cache.insert(pattern, matcher);
    }
}

/// In-memory file index using DashMap for concurrent access
pub struct FileIndex {
    /// Root directory being indexed
    root: PathBuf,

    /// Main index: path -> metadata
    entries: DashMap<PathBuf, FileMetadata>,

    /// Directory children cache: dir_path -> [child_paths]
    dir_children: DashMap<PathBuf, Vec<PathBuf>>,

    /// All file paths (for fast iteration)
    all_files: RwLock<Vec<PathBuf>>,

    /// Whether the index has been built
    is_ready: AtomicBool,

    /// Whether the index is currently being built
    is_building: AtomicBool,

    /// Lock-free cache for compiled glob patterns
    glob_cache: GlobCache,
}

impl FileIndex {
    /// Create a new file index for the given root directory
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            entries: DashMap::new(),
            dir_children: DashMap::new(),
            all_files: RwLock::new(Vec::new()),
            is_ready: AtomicBool::new(false),
            is_building: AtomicBool::new(false),
            glob_cache: GlobCache::new(GLOB_CACHE_SIZE),
        }
    }

    /// Build the index by scanning the directory
    pub fn build(&self) -> Result<()> {
        // Prevent concurrent builds
        if self
            .is_building
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
        {
            return Ok(()); // Already building
        }

        // Clear existing entries
        self.entries.clear();
        self.dir_children.clear();

        let mut all_files = Vec::new();

        // Use the `ignore` crate for fast, parallel directory walking
        // It automatically respects .gitignore files
        let walker = ignore::WalkBuilder::new(&self.root)
            .hidden(false) // Include hidden files
            .git_ignore(true) // Respect .gitignore
            .git_global(true) // Respect global gitignore
            .git_exclude(true) // Respect .git/info/exclude
            .build_parallel();

        use std::sync::Mutex;
        let all_files_mutex = Mutex::new(&mut all_files);

        walker.run(|| {
            Box::new(|entry| {
                if let Ok(entry) = entry {
                    let path = entry.path().to_path_buf();

                    // Skip the root directory itself
                    if path == self.root {
                        return ignore::WalkState::Continue;
                    }

                    // Get metadata
                    if let Ok(metadata) = entry.metadata() {
                        let is_dir = metadata.is_dir();
                        let size = metadata.len();
                        let mtime = metadata
                            .modified()
                            .ok()
                            .and_then(|t| t.duration_since(SystemTime::UNIX_EPOCH).ok())
                            .map(|d| d.as_secs_f64())
                            .unwrap_or(0.0);

                        // Simple binary detection: check first few bytes for null
                        let is_binary = if !is_dir && size > 0 {
                            Self::is_binary_file(&path)
                        } else {
                            false
                        };

                        let file_metadata = FileMetadata {
                            size,
                            mtime,
                            is_dir,
                            is_binary,
                        };

                        self.entries.insert(path.clone(), file_metadata);

                        // Track directory children
                        if let Some(parent) = path.parent() {
                            self.dir_children
                                .entry(parent.to_path_buf())
                                .or_default()
                                .push(path.clone());
                        }

                        // Track all files
                        if !is_dir {
                            if let Ok(mut files) = all_files_mutex.lock() {
                                files.push(path);
                            }
                        }
                    }
                }
                ignore::WalkState::Continue
            })
        });

        // Update the all_files list
        if let Ok(mut files) = self.all_files.write() {
            *files = all_files;
        }

        self.is_ready.store(true, Ordering::SeqCst);
        self.is_building.store(false, Ordering::SeqCst);

        Ok(())
    }

    /// Check if a file is binary by reading the first few bytes
    fn is_binary_file(path: &Path) -> bool {
        use std::io::Read;

        if let Ok(mut file) = std::fs::File::open(path) {
            let mut buffer = [0u8; 512];
            if let Ok(n) = file.read(&mut buffer) {
                // Check for null bytes (common indicator of binary)
                return buffer[..n].contains(&0);
            }
        }
        false
    }

    /// Check if the index is ready
    pub fn is_ready(&self) -> bool {
        self.is_ready.load(Ordering::SeqCst)
    }

    /// Refresh the index
    pub fn refresh(&self) -> Result<()> {
        self.is_ready.store(false, Ordering::SeqCst);
        self.build()
    }

    /// List files matching a glob pattern
    pub fn list(&self, pattern: &str, only_files: bool) -> Result<Vec<String>> {
        use rayon::prelude::*;

        if !self.is_ready() {
            return Err(AgentGearError::IndexNotReady);
        }

        // Fast path: "**/*" matches everything
        let match_all = pattern == "**/*" || pattern == "**";

        let files = self
            .all_files
            .read()
            .map_err(|_| AgentGearError::Internal("Failed to acquire read lock".to_string()))?;

        // Use serial iteration for small datasets (Rayon startup overhead > benefit)
        let use_parallel = files.len() >= PARALLEL_ITER_THRESHOLD;

        let results: Vec<String> = if only_files {
            if match_all {
                // No glob matching needed - just convert paths
                if use_parallel {
                    files
                        .par_iter()
                        .map(|p| self.relative_path_fast(p))
                        .collect()
                } else {
                    files.iter().map(|p| self.relative_path_fast(p)).collect()
                }
            } else {
                let matcher = self.compile_glob(pattern)?;
                if use_parallel {
                    files
                        .par_iter()
                        .filter_map(|path| {
                            let relative = self.relative_path_fast(path);
                            if matcher.is_match(&relative) {
                                Some(relative)
                            } else {
                                None
                            }
                        })
                        .collect()
                } else {
                    files
                        .iter()
                        .filter_map(|path| {
                            let relative = self.relative_path_fast(path);
                            if matcher.is_match(&relative) {
                                Some(relative)
                            } else {
                                None
                            }
                        })
                        .collect()
                }
            }
        } else {
            if match_all {
                self.entries
                    .iter()
                    .map(|entry| self.relative_path_fast(entry.key()))
                    .collect()
            } else {
                let matcher = self.compile_glob(pattern)?;
                self.entries
                    .iter()
                    .filter_map(|entry| {
                        let relative = self.relative_path_fast(entry.key());
                        if matcher.is_match(&relative) {
                            Some(relative)
                        } else {
                            None
                        }
                    })
                    .collect()
            }
        };

        Ok(results)
    }

    /// Match files using glob pattern
    pub fn glob(&self, pattern: &str) -> Result<Vec<String>> {
        self.list(pattern, true)
    }

    /// Get matching files as PathBuf (for internal use by searcher)
    /// Automatically filters out binary files using the index metadata.
    pub fn glob_paths(&self, pattern: &str) -> Result<Vec<PathBuf>> {
        self.glob_paths_with_options(pattern, true)
    }

    /// Get matching files as PathBuf with option to filter binary files
    pub fn glob_paths_with_options(
        &self,
        pattern: &str,
        skip_binary: bool,
    ) -> Result<Vec<PathBuf>> {
        use rayon::prelude::*;

        if !self.is_ready() {
            return Err(AgentGearError::IndexNotReady);
        }

        // Fast path: "**/*" matches everything
        let match_all = pattern == "**/*" || pattern == "**";

        let files = self
            .all_files
            .read()
            .map_err(|_| AgentGearError::Internal("Failed to acquire read lock".to_string()))?;

        // Use serial iteration for small datasets
        let use_parallel = files.len() >= PARALLEL_ITER_THRESHOLD;

        let results: Vec<PathBuf> = if match_all {
            if skip_binary {
                // Filter out binary files using index metadata
                let filter_fn = |path: &&PathBuf| {
                    !self
                        .entries
                        .get(*path)
                        .map(|m| m.is_binary)
                        .unwrap_or(false)
                };
                if use_parallel {
                    files.par_iter().filter(filter_fn).cloned().collect()
                } else {
                    files.iter().filter(filter_fn).cloned().collect()
                }
            } else {
                files.clone()
            }
        } else {
            let matcher = self.compile_glob(pattern)?;
            let filter_fn = |path: &&PathBuf| {
                let relative = self.relative_path_fast(path);
                if !matcher.is_match(&relative) {
                    return false;
                }
                if skip_binary {
                    !self
                        .entries
                        .get(*path)
                        .map(|m| m.is_binary)
                        .unwrap_or(false)
                } else {
                    true
                }
            };
            if use_parallel {
                files.par_iter().filter(filter_fn).cloned().collect()
            } else {
                files.iter().filter(filter_fn).cloned().collect()
            }
        };

        Ok(results)
    }

    /// Get metadata for a path
    pub fn get_metadata(&self, path: &Path) -> Option<FileMetadata> {
        self.entries.get(path).map(|entry| entry.clone())
    }

    /// Get the relative path from the root (optimized version)
    #[inline]
    fn relative_path_fast(&self, path: &Path) -> String {
        // Fast path: try to use the path directly if it's valid UTF-8
        if let Ok(relative) = path.strip_prefix(&self.root) {
            if let Some(s) = relative.to_str() {
                return s.to_owned();
            }
        }
        // Fallback for non-UTF8 paths
        path.strip_prefix(&self.root)
            .unwrap_or(path)
            .to_string_lossy()
            .into_owned()
    }

    /// Get the relative path from the root
    fn relative_path(&self, path: &Path) -> String {
        self.relative_path_fast(path)
    }

    /// Compile a glob pattern with lock-free caching
    #[inline]
    fn compile_glob(&self, pattern: &str) -> Result<GlobMatcher> {
        // Fast path: lock-free cache lookup
        if let Some(matcher) = self.glob_cache.get(pattern) {
            return Ok(matcher);
        }

        // Cache miss: compile and store
        let matcher = Glob::new(pattern)
            .map(|g| g.compile_matcher())
            .map_err(AgentGearError::Glob)?;

        self.glob_cache.insert(pattern.to_string(), matcher.clone());
        Ok(matcher)
    }

    /// Get the root directory
    pub fn root(&self) -> &Path {
        &self.root
    }

    /// Get the number of indexed entries
    #[allow(dead_code)]
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// Check if the index is empty
    #[allow(dead_code)]
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    // ========== Incremental update methods ==========

    /// Add a new path to the index
    pub fn add_path(&self, path: &Path) -> Result<()> {
        // Skip if path doesn't exist
        if !path.exists() {
            return Ok(());
        }

        // Get metadata
        let metadata = std::fs::metadata(path)?;
        let is_dir = metadata.is_dir();
        let size = metadata.len();
        let mtime = metadata
            .modified()
            .ok()
            .and_then(|t| t.duration_since(SystemTime::UNIX_EPOCH).ok())
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0);

        let is_binary = if !is_dir && size > 0 {
            Self::is_binary_file(path)
        } else {
            false
        };

        let file_metadata = FileMetadata {
            size,
            mtime,
            is_dir,
            is_binary,
        };

        // Add to entries
        self.entries.insert(path.to_path_buf(), file_metadata);

        // Update directory children
        if let Some(parent) = path.parent() {
            self.dir_children
                .entry(parent.to_path_buf())
                .or_default()
                .push(path.to_path_buf());
        }

        // Update all_files if it's a file
        if !is_dir {
            if let Ok(mut files) = self.all_files.write() {
                if !files.contains(&path.to_path_buf()) {
                    files.push(path.to_path_buf());
                }
            }
        }

        Ok(())
    }

    /// Update metadata for an existing path
    pub fn update_path(&self, path: &Path) -> Result<()> {
        // Skip if path doesn't exist
        if !path.exists() {
            return Ok(());
        }

        // Get updated metadata
        let metadata = std::fs::metadata(path)?;
        let is_dir = metadata.is_dir();
        let size = metadata.len();
        let mtime = metadata
            .modified()
            .ok()
            .and_then(|t| t.duration_since(SystemTime::UNIX_EPOCH).ok())
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0);

        let is_binary = if !is_dir && size > 0 {
            Self::is_binary_file(path)
        } else {
            false
        };

        let file_metadata = FileMetadata {
            size,
            mtime,
            is_dir,
            is_binary,
        };

        // Update entry
        self.entries.insert(path.to_path_buf(), file_metadata);

        Ok(())
    }

    /// Remove a path from the index
    pub fn remove_path(&self, path: &Path) {
        // Remove from entries
        let removed = self.entries.remove(path);

        // Update directory children
        if let Some(parent) = path.parent() {
            if let Some(mut children) = self.dir_children.get_mut(&parent.to_path_buf()) {
                children.retain(|p| p != path);
            }
        }

        // Remove from dir_children if it was a directory
        self.dir_children.remove(path);

        // Update all_files if it was a file
        if let Some((_, metadata)) = removed {
            if !metadata.is_dir {
                if let Ok(mut files) = self.all_files.write() {
                    files.retain(|p| p != path);
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn create_test_files(dir: &Path) {
        std::fs::create_dir_all(dir.join("src")).unwrap();
        std::fs::create_dir_all(dir.join("tests")).unwrap();

        std::fs::write(dir.join("src/main.rs"), "fn main() {}").unwrap();
        std::fs::write(dir.join("src/lib.rs"), "pub fn lib() {}").unwrap();
        std::fs::write(dir.join("tests/test.rs"), "#[test] fn test() {}").unwrap();
        std::fs::write(dir.join("README.md"), "# Test").unwrap();
    }

    #[test]
    fn test_index_build() {
        let dir = tempdir().unwrap();
        create_test_files(dir.path());

        let index = FileIndex::new(dir.path().to_path_buf());
        index.build().unwrap();

        assert!(index.is_ready());
        assert!(index.len() > 0);
    }

    #[test]
    fn test_list_all() {
        let dir = tempdir().unwrap();
        create_test_files(dir.path());

        let index = FileIndex::new(dir.path().to_path_buf());
        index.build().unwrap();

        let files = index.list("**/*", true).unwrap();
        assert_eq!(files.len(), 4); // 4 files
    }

    #[test]
    fn test_glob_pattern() {
        let dir = tempdir().unwrap();
        create_test_files(dir.path());

        let index = FileIndex::new(dir.path().to_path_buf());
        index.build().unwrap();

        let rs_files = index.glob("**/*.rs").unwrap();
        assert_eq!(rs_files.len(), 3); // main.rs, lib.rs, test.rs

        let src_files = index.glob("src/*").unwrap();
        assert_eq!(src_files.len(), 2); // main.rs, lib.rs
    }

    #[test]
    fn test_metadata() {
        let dir = tempdir().unwrap();
        create_test_files(dir.path());

        let index = FileIndex::new(dir.path().to_path_buf());
        index.build().unwrap();

        let main_rs = dir.path().join("src/main.rs");
        let metadata = index.get_metadata(&main_rs).unwrap();

        assert!(!metadata.is_dir);
        assert!(!metadata.is_binary);
        assert!(metadata.size > 0);
    }
}
