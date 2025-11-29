//! Error types for Agent-Gear

use pyo3::exceptions::{PyIOError, PyRuntimeError, PyValueError};
use pyo3::PyErr;
use thiserror::Error;

/// Main error type for Agent-Gear operations
#[derive(Error, Debug)]
pub enum AgentGearError {
    /// IO error during file operations
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    /// Path not found or invalid
    #[error("Path not found: {0}")]
    PathNotFound(String),

    /// Invalid glob or regex pattern
    #[error("Invalid pattern: {0}")]
    Pattern(String),

    /// Text replacement failed due to non-unique match
    #[error("Text not unique in file: found {0} occurrences")]
    TextNotUnique(usize),

    /// Text not found in file
    #[error("Text not found in file")]
    TextNotFound,

    /// Index is still being built
    #[error("Index is still building, please wait")]
    IndexNotReady,

    /// Glob pattern error
    #[error("Glob error: {0}")]
    Glob(#[from] globset::Error),

    /// Regex pattern error
    #[error("Regex error: {0}")]
    Regex(String),

    /// Generic internal error
    #[error("Internal error: {0}")]
    Internal(String),
}

impl From<AgentGearError> for PyErr {
    fn from(err: AgentGearError) -> PyErr {
        match err {
            AgentGearError::Io(e) => PyIOError::new_err(e.to_string()),
            AgentGearError::PathNotFound(p) => {
                PyValueError::new_err(format!("Path not found: {}", p))
            }
            AgentGearError::Pattern(p) => PyValueError::new_err(format!("Invalid pattern: {}", p)),
            AgentGearError::TextNotUnique(n) => {
                PyValueError::new_err(format!("Text not unique: found {} occurrences", n))
            }
            AgentGearError::TextNotFound => PyValueError::new_err("Text not found in file"),
            AgentGearError::IndexNotReady => {
                PyRuntimeError::new_err("Index is still building, please wait")
            }
            AgentGearError::Glob(e) => PyValueError::new_err(format!("Glob error: {}", e)),
            AgentGearError::Regex(e) => PyValueError::new_err(format!("Regex error: {}", e)),
            AgentGearError::Internal(e) => {
                PyRuntimeError::new_err(format!("Internal error: {}", e))
            }
        }
    }
}

/// Result type alias for Agent-Gear operations
pub type Result<T> = std::result::Result<T, AgentGearError>;
