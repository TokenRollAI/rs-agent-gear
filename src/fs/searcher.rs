//! High-performance search engine
//!
//! Provides grep-like search functionality using the ripgrep core libraries.

use globset::{Glob, GlobMatcher};
use memmap2::Mmap;
use pyo3::prelude::*;
use rayon::prelude::*;
use std::fs::File;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Arc;

use crate::utils::error::{AgentGearError, Result};

/// Search options
#[pyclass]
#[derive(Clone, Debug)]
pub struct SearchOptions {
    /// Case sensitive search
    #[pyo3(get, set)]
    pub case_sensitive: bool,

    /// Maximum number of results
    #[pyo3(get, set)]
    pub max_results: usize,

    /// Maximum file size to search (bytes)
    #[pyo3(get, set)]
    pub max_file_size: u64,

    /// Number of context lines before/after match
    #[pyo3(get, set)]
    pub context_lines: usize,
}

#[pymethods]
impl SearchOptions {
    #[new]
    #[pyo3(signature = (case_sensitive = false, max_results = 1000, max_file_size = 10485760, context_lines = 0))]
    fn new(
        case_sensitive: bool,
        max_results: usize,
        max_file_size: u64,
        context_lines: usize,
    ) -> Self {
        Self {
            case_sensitive,
            max_results,
            max_file_size,
            context_lines,
        }
    }
}

impl Default for SearchOptions {
    fn default() -> Self {
        Self {
            case_sensitive: false,
            max_results: 1000,
            max_file_size: 10 * 1024 * 1024, // 10MB
            context_lines: 0,
        }
    }
}

/// A single search result
#[pyclass]
#[derive(Clone, Debug)]
pub struct SearchResult {
    /// File path where match was found
    #[pyo3(get)]
    pub file: String,

    /// Line number (1-indexed)
    #[pyo3(get)]
    pub line_number: u32,

    /// The matching line content
    #[pyo3(get)]
    pub content: String,

    /// Context lines before the match
    #[pyo3(get)]
    pub context_before: Vec<String>,

    /// Context lines after the match
    #[pyo3(get)]
    pub context_after: Vec<String>,
}

#[pymethods]
impl SearchResult {
    fn __repr__(&self) -> String {
        format!(
            "SearchResult(file='{}', line={}, content='{}')",
            self.file,
            self.line_number,
            if self.content.len() > 50 {
                format!("{}...", &self.content[..50])
            } else {
                self.content.clone()
            }
        )
    }
}

/// Search engine for file content
pub struct Searcher {
    root: PathBuf,
}

impl Searcher {
    /// Create a new searcher for the given root directory
    pub fn new(root: PathBuf) -> Self {
        Self { root }
    }

    /// Search for a pattern in files matching the glob pattern
    pub fn grep(
        &self,
        py: Python<'_>,
        query: &str,
        glob_pattern: &str,
        options: &SearchOptions,
    ) -> PyResult<Vec<SearchResult>> {
        py.allow_threads(|| self.grep_internal(query, glob_pattern, options, None))
            .map_err(|e| e.into())
    }

    /// Search for a pattern using pre-collected files from index
    pub fn grep_with_files(
        &self,
        py: Python<'_>,
        query: &str,
        files: Vec<PathBuf>,
        options: &SearchOptions,
    ) -> PyResult<Vec<SearchResult>> {
        py.allow_threads(|| self.grep_internal(query, "**/*", options, Some(files)))
            .map_err(|e| e.into())
    }

    fn grep_internal(
        &self,
        query: &str,
        glob_pattern: &str,
        options: &SearchOptions,
        pre_collected_files: Option<Vec<PathBuf>>,
    ) -> Result<Vec<SearchResult>> {
        // Build regex pattern
        let regex = if options.case_sensitive {
            regex::Regex::new(query)
        } else {
            regex::RegexBuilder::new(query)
                .case_insensitive(true)
                .build()
        }
        .map_err(|e| AgentGearError::Regex(e.to_string()))?;

        // Get files to search
        let files = if let Some(files) = pre_collected_files {
            files
        } else {
            let glob_matcher = Glob::new(glob_pattern)
                .map(|g| g.compile_matcher())
                .map_err(AgentGearError::Glob)?;
            self.collect_files(&glob_matcher, options.max_file_size)?
        };

        // Counter for limiting results
        let result_count = Arc::new(AtomicUsize::new(0));
        let max_results = options.max_results;
        let cancelled = Arc::new(AtomicBool::new(false));

        // Search files in parallel
        let results: Vec<SearchResult> = files
            .par_iter()
            .flat_map(|path| {
                if cancelled.load(Ordering::Relaxed) {
                    return Vec::new();
                }

                // Check if we've hit the limit
                if result_count.load(Ordering::Relaxed) >= max_results {
                    return Vec::new();
                }

                self.search_file(
                    path,
                    &regex,
                    options,
                    &result_count,
                    &cancelled,
                    max_results,
                )
                .unwrap_or_default()
            })
            .collect();

        // Truncate to max_results (parallel collection may slightly exceed)
        let results: Vec<SearchResult> = results.into_iter().take(max_results).collect();

        Ok(results)
    }

    /// Collect files matching the glob pattern
    fn collect_files(&self, glob_matcher: &GlobMatcher, max_size: u64) -> Result<Vec<PathBuf>> {
        use ignore::WalkState;
        use std::sync::Mutex;

        let files = Mutex::new(Vec::new());

        let walker = ignore::WalkBuilder::new(&self.root)
            .hidden(false)
            .git_ignore(true)
            .build_parallel();

        walker.run(|| {
            Box::new(|entry| {
                let entry = match entry {
                    Ok(e) => e,
                    Err(_) => return WalkState::Continue,
                };

                let path = entry.path();

                // Skip directories
                if path.is_dir() {
                    return WalkState::Continue;
                }

                // Check file size
                if let Ok(metadata) = entry.metadata() {
                    if metadata.len() > max_size {
                        return WalkState::Continue;
                    }
                }

                // Check glob pattern
                let relative = path.strip_prefix(&self.root).unwrap_or(path);

                if glob_matcher.is_match(relative) && !Self::is_binary_file(path) {
                    if let Ok(mut guard) = files.lock() {
                        guard.push(path.to_path_buf());
                    }
                }

                WalkState::Continue
            })
        });

        Ok(files.into_inner().unwrap_or_default())
    }

    /// Search a single file for matches using mmap for large files
    fn search_file(
        &self,
        path: &Path,
        regex: &regex::Regex,
        options: &SearchOptions,
        result_count: &Arc<AtomicUsize>,
        cancel_flag: &AtomicBool,
        max_results: usize,
    ) -> Result<Vec<SearchResult>> {
        if cancel_flag.load(Ordering::Relaxed) {
            return Ok(Vec::new());
        }

        // Get file size
        let metadata = match std::fs::metadata(path) {
            Ok(m) => m,
            Err(_) => return Ok(Vec::new()),
        };

        let file_size = metadata.len() as usize;

        // Use mmap for larger files (> 32KB), regular read for smaller
        let content: String = if file_size > 32 * 1024 {
            // Memory-mapped read
            let file = match File::open(path) {
                Ok(f) => f,
                Err(_) => return Ok(Vec::new()),
            };
            let mmap = match unsafe { Mmap::map(&file) } {
                Ok(m) => m,
                Err(_) => return Ok(Vec::new()),
            };
            match std::str::from_utf8(&mmap) {
                Ok(s) => s.to_string(),
                Err(_) => return Ok(Vec::new()), // Skip non-UTF8 files
            }
        } else {
            // Regular read for small files
            match std::fs::read_to_string(path) {
                Ok(c) => c,
                Err(_) => return Ok(Vec::new()),
            }
        };

        let lines: Vec<&str> = content.lines().collect();
        let mut results = Vec::new();

        let relative_path = path
            .strip_prefix(&self.root)
            .unwrap_or(path)
            .to_string_lossy()
            .to_string();

        for (i, line) in lines.iter().enumerate() {
            // Check if we've hit the limit
            if cancel_flag.load(Ordering::Relaxed)
                || result_count.load(Ordering::Relaxed) >= max_results
            {
                break;
            }

            if regex.is_match(line) {
                // Collect context lines
                let context_before: Vec<String> = if options.context_lines > 0 {
                    let start = i.saturating_sub(options.context_lines);
                    lines[start..i].iter().map(|s| s.to_string()).collect()
                } else {
                    Vec::new()
                };

                let context_after: Vec<String> = if options.context_lines > 0 {
                    let end = (i + 1 + options.context_lines).min(lines.len());
                    lines[(i + 1)..end].iter().map(|s| s.to_string()).collect()
                } else {
                    Vec::new()
                };

                let updated =
                    result_count.fetch_update(Ordering::Relaxed, Ordering::Relaxed, |current| {
                        if current >= max_results {
                            None
                        } else {
                            Some(current + 1)
                        }
                    });

                match updated {
                    Ok(prev) => {
                        results.push(SearchResult {
                            file: relative_path.clone(),
                            line_number: (i + 1) as u32,
                            content: line.to_string(),
                            context_before,
                            context_after,
                        });

                        if prev + 1 >= max_results {
                            cancel_flag.store(true, Ordering::Relaxed);
                            break;
                        }
                    }
                    Err(_) => {
                        cancel_flag.store(true, Ordering::Relaxed);
                        break;
                    }
                }
            }
        }

        Ok(results)
    }

    /// Check if a file appears to be binary
    fn is_binary_file(path: &Path) -> bool {
        use std::io::Read;

        if let Ok(mut file) = std::fs::File::open(path) {
            let mut buffer = [0u8; 512];
            if let Ok(n) = file.read(&mut buffer) {
                return buffer[..n].contains(&0);
            }
        }
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn create_test_files(dir: &Path) {
        std::fs::create_dir_all(dir.join("src")).unwrap();

        std::fs::write(
            dir.join("src/main.rs"),
            r#"fn main() {
    println!("Hello, World!");
}
"#,
        )
        .unwrap();

        std::fs::write(
            dir.join("src/lib.rs"),
            r#"pub fn hello() {
    println!("Hello from lib!");
}

pub fn goodbye() {
    println!("Goodbye!");
}
"#,
        )
        .unwrap();

        std::fs::write(dir.join("README.md"), "# Hello Project\n\nThis is a test.").unwrap();
    }

    #[test]
    fn test_search_basic() {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let dir = tempdir().unwrap();
            create_test_files(dir.path());

            let searcher = Searcher::new(dir.path().to_path_buf());
            let options = SearchOptions::default();

            let results = searcher.grep(py, "Hello", "**/*", &options).unwrap();
            assert!(!results.is_empty());
        });
    }

    #[test]
    fn test_search_glob_filter() {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let dir = tempdir().unwrap();
            create_test_files(dir.path());

            let searcher = Searcher::new(dir.path().to_path_buf());
            let options = SearchOptions::default();

            // Only search .rs files
            let results = searcher.grep(py, "println", "**/*.rs", &options).unwrap();
            assert!(results.len() >= 2);

            // Verify all results are from .rs files
            for result in &results {
                assert!(result.file.ends_with(".rs"));
            }
        });
    }

    #[test]
    fn test_search_case_insensitive() {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let dir = tempdir().unwrap();
            create_test_files(dir.path());

            let searcher = Searcher::new(dir.path().to_path_buf());

            // Case insensitive (default)
            let options = SearchOptions {
                case_sensitive: false,
                ..Default::default()
            };
            let results = searcher.grep(py, "hello", "**/*", &options).unwrap();
            assert!(!results.is_empty());

            // Case sensitive
            let options = SearchOptions {
                case_sensitive: true,
                ..Default::default()
            };
            let results = searcher.grep(py, "hello", "**/*", &options).unwrap();
            // "hello" (lowercase) should not match "Hello"
            let hello_count = results
                .iter()
                .filter(|r| r.content.contains("hello"))
                .count();
            assert_eq!(hello_count, 0);
        });
    }

    #[test]
    fn test_search_max_results() {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let dir = tempdir().unwrap();
            create_test_files(dir.path());

            let searcher = Searcher::new(dir.path().to_path_buf());
            let options = SearchOptions {
                max_results: 1,
                ..Default::default()
            };

            let results = searcher.grep(py, "println", "**/*", &options).unwrap();
            assert_eq!(results.len(), 1);
        });
    }
}
