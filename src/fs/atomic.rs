//! Atomic file write operations
//!
//! Implements the "write to temp -> fsync -> rename" pattern for atomic file updates.
//! This ensures that file writes are atomic even if the process crashes during the write.

use std::io::Write;
use std::path::Path;

use crate::utils::error::{AgentGearError, Result};

/// Write content to a file atomically
///
/// This function:
/// 1. Creates a temporary file in the same directory as the target
/// 2. Writes the content to the temporary file
/// 3. Calls fsync to ensure data is flushed to disk
/// 4. Atomically renames the temporary file to the target path
///
/// # Arguments
/// * `path` - Target file path
/// * `content` - Bytes to write
///
/// # Errors
/// Returns an error if any step fails. The original file (if any) is left unchanged
/// if an error occurs.
pub fn atomic_write(path: &Path, content: &[u8]) -> Result<()> {
    // Get the parent directory (or current dir if none)
    let dir = path.parent().unwrap_or(Path::new("."));

    // Ensure the directory exists
    if !dir.exists() {
        std::fs::create_dir_all(dir)?;
    }

    // Create a temporary file in the same directory
    // This ensures the rename is atomic (same filesystem)
    let mut temp_file = tempfile::NamedTempFile::new_in(dir)?;

    // Write content
    temp_file.write_all(content)?;

    // Flush and sync to disk
    temp_file.as_file().sync_all()?;

    // Atomically rename to target path
    temp_file.persist(path).map_err(|e| {
        AgentGearError::Io(std::io::Error::new(
            std::io::ErrorKind::Other,
            format!("Failed to persist file: {}", e),
        ))
    })?;

    Ok(())
}

/// Write content to a file atomically, preserving permissions
///
/// Similar to `atomic_write`, but preserves the original file's permissions
/// if the file already exists.
#[allow(dead_code)]
pub fn atomic_write_preserve_perms(path: &Path, content: &[u8]) -> Result<()> {
    // Get original permissions if file exists
    let original_perms = path.metadata().ok().map(|m| m.permissions());

    // Perform atomic write
    atomic_write(path, content)?;

    // Restore permissions if we had them
    if let Some(perms) = original_perms {
        std::fs::set_permissions(path, perms)?;
    }

    Ok(())
}

/// Append content to a file atomically
///
/// Reads the existing content, appends the new content, and writes atomically.
#[allow(dead_code)]
pub fn atomic_append(path: &Path, content: &[u8]) -> Result<()> {
    let existing = if path.exists() {
        std::fs::read(path)?
    } else {
        Vec::new()
    };

    let mut combined = existing;
    combined.extend_from_slice(content);

    atomic_write(path, &combined)
}

/// Create a backup of a file before modifying it
#[allow(dead_code)]
pub fn create_backup(path: &Path) -> Result<std::path::PathBuf> {
    let backup_path = path.with_extension(format!(
        "{}.bak",
        path.extension().and_then(|e| e.to_str()).unwrap_or("")
    ));

    std::fs::copy(path, &backup_path)?;
    Ok(backup_path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_atomic_write() {
        let dir = tempdir().unwrap();
        let file_path = dir.path().join("test.txt");

        atomic_write(&file_path, b"Hello, World!").unwrap();

        let content = std::fs::read_to_string(&file_path).unwrap();
        assert_eq!(content, "Hello, World!");
    }

    #[test]
    fn test_atomic_write_overwrite() {
        let dir = tempdir().unwrap();
        let file_path = dir.path().join("test.txt");

        // Write initial content
        atomic_write(&file_path, b"Initial").unwrap();

        // Overwrite
        atomic_write(&file_path, b"Overwritten").unwrap();

        let content = std::fs::read_to_string(&file_path).unwrap();
        assert_eq!(content, "Overwritten");
    }

    #[test]
    fn test_atomic_write_creates_directory() {
        let dir = tempdir().unwrap();
        let file_path = dir.path().join("subdir").join("test.txt");

        atomic_write(&file_path, b"Content").unwrap();

        assert!(file_path.exists());
        let content = std::fs::read_to_string(&file_path).unwrap();
        assert_eq!(content, "Content");
    }

    #[test]
    fn test_atomic_append() {
        let dir = tempdir().unwrap();
        let file_path = dir.path().join("test.txt");

        atomic_write(&file_path, b"Hello").unwrap();
        atomic_append(&file_path, b", World!").unwrap();

        let content = std::fs::read_to_string(&file_path).unwrap();
        assert_eq!(content, "Hello, World!");
    }
}
