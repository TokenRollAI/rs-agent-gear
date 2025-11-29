# 文件监听系统

## 概述

Agent-Gear 的文件监听系统提供实时的文件系统变动检测，自动保持内存索引与磁盘状态同步。

## 架构

```
FileSystem
    │
    ├── FileWatcher (后台线程)
    │   ├── notify::RecommendedWatcher (跨平台事件源)
    │   ├── Debouncer (事件防抖)
    │   └── crossbeam::channel (事件通道)
    │
    └── FileIndex
        ├── add_path() (创建事件)
        ├── update_path() (修改事件)
        └── remove_path() (删除事件)
```

## 关键组件

### FileWatcher (`src/fs/watcher.rs`)

跨平台文件监听器，使用 `notify` crate：

- **Linux**: inotify
- **macOS**: FSEvents
- **Windows**: ReadDirectoryChangesW

```rust
pub struct FileWatcher {
    _watcher: RecommendedWatcher,
    event_rx: Receiver<notify::Result<Event>>,
    debouncer: RwLock<Debouncer>,
    running: Arc<AtomicBool>,
}
```

### Debouncer

事件防抖器，合并高频事件：

- **防抖时间**: 100ms
- **事件合并**:
  - Created + Deleted = 无事件
  - Created + Modified = Created
  - 后续事件覆盖前序事件

### ChangeKind

事件类型枚举：

```rust
pub enum ChangeKind {
    Created,               // 文件/目录创建
    Modified,              // 文件内容修改
    Deleted,               // 文件/目录删除
    Renamed { from, to },  // 重命名
}
```

## Python API

```python
from agent_gear import FileSystem

# 启用监听（默认）
fs = FileSystem("/path/to/project", auto_watch=True)

# 检查监听状态
if fs.is_watching():
    print("File watching is active")

# 关闭时自动停止监听
fs.close()
```

## 索引增量更新

监听线程自动更新索引：

```python
# 创建新文件
Path("new_file.py").write_text("# new")

# 索引自动更新（无需手动刷新）
# 新文件会出现在 list 结果中
files = fs.list("**/*.py")
```

## 性能考虑

| 场景 | 影响 |
|------|------|
| 大量文件创建 | 防抖合并减少处理次数 |
| 高频写入 | 100ms 窗口内合并为一次更新 |
| 监听开销 | 后台线程，不阻塞主线程 |

## 跨平台注意事项

### Linux
- inotify watches 限制：`/proc/sys/fs/inotify/max_user_watches`
- 大型项目可能需要增加限制

### macOS
- FSEvents 延迟约 1 秒
- 批量事件合并

### Windows
- ReadDirectoryChangesW 异步高效
- 需要管理员权限访问某些目录

## 禁用监听

对于只读场景或性能敏感场景：

```python
# 禁用监听
fs = FileSystem("/path/to/project", auto_watch=False)

# 手动刷新索引
fs.refresh()
```
