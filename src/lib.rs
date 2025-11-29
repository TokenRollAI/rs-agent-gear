//! Agent-Gear: High-performance filesystem operations for AI agents
//!
//! This crate provides a Python extension module that offers:
//! - Stateful in-memory file indexing
//! - Batch file I/O operations
//! - High-performance grep search
//! - File watching with debouncing

use pyo3::prelude::*;

pub mod fs;
pub mod utils;

use fs::FileSystem;

/// Agent-Gear Python module
#[pymodule]
fn _rust_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Register the FileSystem class
    m.add_class::<FileSystem>()?;

    // Register search result types
    m.add_class::<fs::searcher::SearchResult>()?;
    m.add_class::<fs::searcher::SearchOptions>()?;

    // Register metadata types
    m.add_class::<fs::index::FileMetadata>()?;

    // Module version
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;

    Ok(())
}
