//! File system watcher
//!
//! Provides real-time file system monitoring with debouncing to keep
//! the in-memory index synchronized with disk changes.

use crossbeam::channel::{unbounded, Receiver, Sender};
use notify::{
    event::{CreateKind, ModifyKind, RemoveKind, RenameMode},
    Config, Event, EventKind, RecommendedWatcher, RecursiveMode, Watcher,
};
use parking_lot::RwLock;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant};

use crate::utils::error::{AgentGearError, Result};

/// File change event types
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ChangeKind {
    /// File or directory was created
    Created,
    /// File content was modified
    Modified,
    /// File or directory was deleted
    Deleted,
    /// File or directory was renamed
    Renamed { from: PathBuf, to: PathBuf },
}

/// A debounced file change event
#[derive(Debug, Clone)]
pub struct FileChange {
    /// The path that changed
    pub path: PathBuf,
    /// The type of change
    pub kind: ChangeKind,
    /// Timestamp of the change
    pub timestamp: Instant,
}

/// Debouncer for file system events
///
/// Collects events over a time window and merges them to reduce noise.
pub struct Debouncer {
    /// Pending events by path
    pending: HashMap<PathBuf, (ChangeKind, Instant)>,
    /// Debounce duration
    duration: Duration,
}

impl Debouncer {
    /// Create a new debouncer with the given duration
    pub fn new(duration: Duration) -> Self {
        Self {
            pending: HashMap::new(),
            duration,
        }
    }

    /// Add an event to the debouncer
    pub fn add_event(&mut self, path: PathBuf, kind: ChangeKind) {
        let now = Instant::now();

        // Merge events: later events override earlier ones
        // Exception: Delete after Create = no event
        if let Some((existing_kind, _)) = self.pending.get(&path) {
            match (existing_kind, &kind) {
                // Created then deleted = nothing happened
                (ChangeKind::Created, ChangeKind::Deleted) => {
                    self.pending.remove(&path);
                    return;
                }
                // Created then modified = still created
                (ChangeKind::Created, ChangeKind::Modified) => {
                    return; // Keep Created
                }
                _ => {}
            }
        }

        self.pending.insert(path, (kind, now));
    }

    /// Get events that have been stable for the debounce duration
    pub fn flush(&mut self) -> Vec<FileChange> {
        let now = Instant::now();
        let mut ready = Vec::new();
        let mut to_remove = Vec::new();

        for (path, (kind, timestamp)) in self.pending.iter() {
            if now.duration_since(*timestamp) >= self.duration {
                ready.push(FileChange {
                    path: path.clone(),
                    kind: kind.clone(),
                    timestamp: *timestamp,
                });
                to_remove.push(path.clone());
            }
        }

        for path in to_remove {
            self.pending.remove(&path);
        }

        ready
    }

    /// Force flush all pending events regardless of timing
    pub fn flush_all(&mut self) -> Vec<FileChange> {
        let events: Vec<FileChange> = self
            .pending
            .drain()
            .map(|(path, (kind, timestamp))| FileChange {
                path,
                kind,
                timestamp,
            })
            .collect();
        events
    }

    /// Check if there are pending events
    pub fn has_pending(&self) -> bool {
        !self.pending.is_empty()
    }
}

/// File system watcher with debouncing
pub struct FileWatcher {
    /// The underlying notify watcher
    _watcher: RecommendedWatcher,
    /// Channel receiver for events
    event_rx: Receiver<notify::Result<Event>>,
    /// Root directory being watched
    root: PathBuf,
    /// Debouncer instance
    debouncer: RwLock<Debouncer>,
    /// Whether the watcher is running
    running: Arc<std::sync::atomic::AtomicBool>,
}

impl FileWatcher {
    /// Create a new file watcher for the given root directory
    pub fn new(root: PathBuf, debounce_duration: Duration) -> Result<Self> {
        let (tx, rx): (
            Sender<notify::Result<Event>>,
            Receiver<notify::Result<Event>>,
        ) = unbounded();

        // Create the watcher with a simple event handler
        let mut watcher = RecommendedWatcher::new(
            move |res| {
                let _ = tx.send(res);
            },
            Config::default().with_poll_interval(Duration::from_millis(100)),
        )
        .map_err(|e| AgentGearError::Internal(format!("Failed to create watcher: {}", e)))?;

        // Start watching the root directory recursively
        watcher
            .watch(&root, RecursiveMode::Recursive)
            .map_err(|e| AgentGearError::Internal(format!("Failed to watch directory: {}", e)))?;

        Ok(Self {
            _watcher: watcher,
            event_rx: rx,
            root,
            debouncer: RwLock::new(Debouncer::new(debounce_duration)),
            running: Arc::new(std::sync::atomic::AtomicBool::new(true)),
        })
    }

    /// Process pending events from the watcher
    ///
    /// This should be called periodically to collect and debounce events.
    pub fn process_events(&self) -> Vec<FileChange> {
        // Collect all pending raw events to minimize lock duration/frequency
        let mut raw_events = Vec::new();
        while let Ok(event_result) = self.event_rx.try_recv() {
            if let Ok(event) = event_result {
                raw_events.push(event);
            }
        }

        let mut debouncer = self.debouncer.write();

        for event in raw_events {
            let kind = match event.kind {
                EventKind::Create(CreateKind::File | CreateKind::Folder) => ChangeKind::Created,
                EventKind::Create(CreateKind::Any) => ChangeKind::Created,
                EventKind::Modify(ModifyKind::Data(_)) => ChangeKind::Modified,
                EventKind::Modify(ModifyKind::Name(RenameMode::Both)) => {
                    // Handle rename: paths[0] = from, paths[1] = to
                    if event.paths.len() >= 2 {
                        debouncer.add_event(
                            event.paths[0].clone(),
                            ChangeKind::Renamed {
                                from: event.paths[0].clone(),
                                to: event.paths[1].clone(),
                            },
                        );
                    }
                    continue;
                }
                EventKind::Modify(ModifyKind::Name(RenameMode::From)) => ChangeKind::Deleted,
                EventKind::Modify(ModifyKind::Name(RenameMode::To)) => ChangeKind::Created,
                EventKind::Remove(RemoveKind::File | RemoveKind::Folder) => ChangeKind::Deleted,
                EventKind::Remove(RemoveKind::Any) => ChangeKind::Deleted,
                _ => continue, // Ignore other events
            };

            for path in event.paths {
                debouncer.add_event(path, kind.clone());
            }
        }

        // Flush debounced events
        debouncer.flush()
    }

    /// Get the root directory being watched
    pub fn root(&self) -> &Path {
        &self.root
    }

    /// Check if the watcher is still running
    pub fn is_running(&self) -> bool {
        self.running.load(std::sync::atomic::Ordering::SeqCst)
    }

    /// Stop the watcher
    pub fn stop(&self) {
        self.running
            .store(false, std::sync::atomic::Ordering::SeqCst);
    }
}

impl Drop for FileWatcher {
    fn drop(&mut self) {
        self.stop();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread;
    use tempfile::tempdir;

    #[test]
    fn test_debouncer_basic() {
        let mut debouncer = Debouncer::new(Duration::from_millis(50));

        debouncer.add_event(PathBuf::from("/test/file.txt"), ChangeKind::Created);

        // Should not flush immediately
        let events = debouncer.flush();
        assert!(events.is_empty());

        // Wait for debounce
        thread::sleep(Duration::from_millis(60));

        let events = debouncer.flush();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].path, PathBuf::from("/test/file.txt"));
    }

    #[test]
    fn test_debouncer_merge_create_delete() {
        let mut debouncer = Debouncer::new(Duration::from_millis(50));

        debouncer.add_event(PathBuf::from("/test/file.txt"), ChangeKind::Created);
        debouncer.add_event(PathBuf::from("/test/file.txt"), ChangeKind::Deleted);

        // Created + Deleted = nothing
        assert!(!debouncer.has_pending());
    }

    #[test]
    fn test_debouncer_merge_create_modify() {
        let mut debouncer = Debouncer::new(Duration::from_millis(50));

        debouncer.add_event(PathBuf::from("/test/file.txt"), ChangeKind::Created);
        debouncer.add_event(PathBuf::from("/test/file.txt"), ChangeKind::Modified);

        thread::sleep(Duration::from_millis(60));

        let events = debouncer.flush();
        assert_eq!(events.len(), 1);
        // Should still be Created (not Modified)
        assert!(matches!(events[0].kind, ChangeKind::Created));
    }

    #[test]
    fn test_watcher_creation() {
        let dir = tempdir().unwrap();
        let watcher = FileWatcher::new(dir.path().to_path_buf(), Duration::from_millis(100));
        assert!(watcher.is_ok());
    }

    #[test]
    fn test_watcher_detects_file_creation() {
        let dir = tempdir().unwrap();
        let watcher =
            FileWatcher::new(dir.path().to_path_buf(), Duration::from_millis(50)).unwrap();

        // Create a file
        let file_path = dir.path().join("new_file.txt");
        std::fs::write(&file_path, "test content").unwrap();

        // Wait for events
        thread::sleep(Duration::from_millis(200));

        let events = watcher.process_events();

        // Should have detected the creation
        let created_events: Vec<_> = events
            .iter()
            .filter(|e| matches!(e.kind, ChangeKind::Created))
            .collect();

        assert!(!created_events.is_empty(), "Should detect file creation");
    }

    #[test]
    fn test_watcher_detects_file_modification() {
        let dir = tempdir().unwrap();

        // Create file before watching
        let file_path = dir.path().join("existing.txt");
        std::fs::write(&file_path, "initial").unwrap();

        let watcher =
            FileWatcher::new(dir.path().to_path_buf(), Duration::from_millis(50)).unwrap();

        // Modify the file
        std::fs::write(&file_path, "modified").unwrap();

        // Wait for events
        thread::sleep(Duration::from_millis(200));

        let events = watcher.process_events();

        // Should have detected the modification
        assert!(!events.is_empty(), "Should detect file modification");
    }

    #[test]
    fn test_watcher_detects_file_deletion() {
        let dir = tempdir().unwrap();

        // Create file before watching
        let file_path = dir.path().join("to_delete.txt");
        std::fs::write(&file_path, "content").unwrap();

        let watcher =
            FileWatcher::new(dir.path().to_path_buf(), Duration::from_millis(50)).unwrap();

        // Delete the file
        std::fs::remove_file(&file_path).unwrap();

        // Wait for events
        thread::sleep(Duration::from_millis(200));

        let events = watcher.process_events();

        let deleted_events: Vec<_> = events
            .iter()
            .filter(|e| matches!(e.kind, ChangeKind::Deleted))
            .collect();

        assert!(!deleted_events.is_empty(), "Should detect file deletion");
    }
}
