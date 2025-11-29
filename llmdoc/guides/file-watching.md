# 如何配置和使用文件监听系统

## 步骤 1: 启用文件监听

创建 FileSystem 实例，默认启用文件监听：

```python
from agent_gear import FileSystem

# 启用监听（默认行为）
fs = FileSystem("/path/to/project", auto_watch=True)

# 等待初始索引完成
while not fs.is_ready():
    time.sleep(0.1)

# 现在可以列出文件
files = fs.list("**/*.py")
```

**说明**：设置 `auto_watch=True` 后，FileSystem 会启动两个后台线程：一个构建初始索引，一个持续监听文件变动。

**验证方式**：调用 `fs.is_watching()` 检查监听是否活跃，应返回 `True`。

## 步骤 2: 理解索引自动同步机制

当文件系统发生变动时，监听线程自动更新索引，无需手动干预：

```python
from pathlib import Path

# 创建新文件
Path("new_module.py").write_text("# 新模块")

# 等待防抖稳定（≤100ms）
time.sleep(0.15)

# 新文件立即出现在索引中
files = fs.list("**/*.py")
assert "new_module.py" in files
```

**工作原理**：
1. 文件系统触发 `Create` 事件
2. FileWatcher 通过 notify crate 捕获事件
3. Debouncer 在 100ms 防抖窗口内合并事件
4. 稳定的 `Created` 事件调用 `FileIndex::add_path()`
5. 新文件出现在 `list()` 结果中

## 步骤 3: 处理事件流

监听线程每 50ms 处理一次事件。若需显式获取待处理事件计数：

```python
# 获取最近处理的事件数
change_count = fs.pending_changes()
print(f"Processed {change_count} events")

# 该方法会触发一次事件刷新并返回刷新出的事件数
```

**常见场景**：
- 批量修改文件后，调用 `pending_changes()` 验证所有变动已被索引
- 对时间敏感的操作，可在调用后加 `time.sleep(0.2)` 确保防抖完成

## 步骤 4: 在只读或高性能场景中禁用监听

对于不需要自动同步的场景（如生产环境只读访问），禁用监听以节省资源：

```python
# 禁用监听
fs = FileSystem("/path/to/project", auto_watch=False)

# 等待初始索引
while not fs.is_ready():
    time.sleep(0.1)

# 手动刷新索引（必要时）
fs.refresh()
```

**性能影响**：禁用监听可减少后台线程开销，但失去实时同步能力。

## 步骤 5: 跨平台注意事项

### Linux (inotify)

inotify 有系统级监听限制，大型项目需增加配置：

```bash
# 查看当前限制
cat /proc/sys/fs/inotify/max_user_watches

# 临时增加（需 root）
echo 524288 | sudo tee /proc/sys/fs/inotify/max_user_watches

# 永久修改：编辑 /etc/sysctl.conf
fs.inotify.max_user_watches = 524288
```

**症状**：如果项目有 > 8000 个文件且无法监听，会看到错误日志 "Failed to watch directory"。

**应对方案**：若无权修改系统配置，可切换到 `auto_watch=False` 并手动刷新。

### macOS (FSEvents)

FSEvents 延迟约 1 秒，且采用批量事件模式：

```python
# FSEvents 可能合并多个快速事件为一个
Path("file1.txt").write_text("a")
Path("file2.txt").write_text("b")
time.sleep(1.5)  # 等待批处理完成
```

**优化建议**：对于大量文件操作，使用 Debouncer 的 100ms 防抖已经有效减少事件数。

### Windows (ReadDirectoryChangesW)

ReadDirectoryChangesW 异步高效，无特殊注意事项：

```python
# Windows 下 NTFS 长路径需要特殊处理
# FileSystem 自动处理，无需手动干预
```

**权限问题**：某些系统目录（如 System32）需管理员权限，若遇到权限错误可捕获异常并回退到 `auto_watch=False`。

## 步骤 6: 性能调优

### 防抖窗口优化

Debouncer 使用固定 100ms 防抖窗口（`src/fs/watcher.rs:153`），适合大多数场景。若需修改：

**当前配置**：
```rust
FileWatcher::new(root_path, Duration::from_millis(100))
```

**调优场景**：
- **降低延迟**：减少到 50ms（需修改源码并重新编译）
  - 适用于实时编辑场景
  - 代价：更多微小事件不被合并，索引更新频繁

- **提高合并率**：增加到 200ms（需修改源码）
  - 适用于批量导入数据
  - 代价：用户感知的延迟增加

### 监听线程轮询间隔

轮询间隔为 50ms（`src/fs/mod.rs:358`），平衡反应速度和 CPU 开销。

**性能指标**：
- 单核 CPU 占用：< 1%
- 事件延迟（p99）：≤ 150ms（防抖 + 轮询）
- 内存开销：< 10MB（主要来自 Debouncer HashMap）

### 仅监听特定目录

若项目目录复杂，可考虑在应用层过滤，而非在文件系统监听层：

```python
# 只关心 src 目录的 Python 文件
files = fs.list("src/**/*.py")

# FileWatcher 仍监听全部目录，但应用层只处理需要的文件
```

注意：FileWatcher 无法配置为仅监听子目录（notify crate 限制），完整递归监听是唯一方案。

## 步骤 7: 错误处理和恢复

### 监听失败自动降级

若 FileWatcher 创建失败（如 inotify 限制），FileSystem 自动降级到无监听模式：

```python
fs = FileSystem("/path", auto_watch=True)

if not fs.is_watching():
    # 监听启动失败，已自动降级
    # 需手动调用 refresh() 更新索引
    fs.refresh()
```

检查日志获取详细错误信息：
```
Failed to start file watcher: ...
```

### 索引不一致恢复

若怀疑索引与磁盘不一致，手动刷新索引：

```python
# 强制重建索引（耗时，仅在必要时调用）
fs.refresh()

# 等待重建完成
while not fs.is_ready():
    time.sleep(0.1)
```

## 步骤 8: 上下文管理器的正确用法

使用 `with` 语句确保资源正确清理：

```python
with FileSystem("/path/to/project") as fs:
    # 自动启动监听线程
    while not fs.is_ready():
        time.sleep(0.1)

    # 执行文件操作
    files = fs.list("**/*.py")

    # 离开 with 块时自动调用 close()
    # 监听线程停止，资源释放
```

**等价的手动管理**：
```python
fs = FileSystem("/path/to/project")
try:
    # ... 使用 fs
    pass
finally:
    fs.close()  # 必须显式调用
```

## 常见问题

### Q: 文件修改后为什么 list() 结果没有变化？

**A**: 100ms 防抖窗口尚未完成。等待 ≤150ms 后重试：
```python
time.sleep(0.15)
files = fs.list()
```

### Q: 批量删除文件后索引为什么还包含这些文件？

**A**: 删除事件可能未被监听到（如外部进程删除）。调用 `refresh()` 强制重建：
```python
fs.refresh()
while not fs.is_ready():
    time.sleep(0.1)
```

### Q: 监听线程是否会消耗大量 CPU？

**A**: 否。50ms 轮询 + 防抖合并，单核占用 < 1%。若占用异常高，检查：
1. 文件系统是否有大量频繁变动（如编译中间文件）
2. 是否应该配置 `.gitignore` 排除不必要的目录

### Q: 如何判断监听是否活跃？

**A**: 调用 `is_watching()`：
```python
if fs.is_watching():
    print("监听活跃")
else:
    print("监听已停止或未启动")
```

### Q: 创建大量文件时性能如何？

**A**: Debouncer 自动合并事件。100 个文件创建在 100ms 内会合并为最多 100 个单独的 `Created` 事件，索引在 50ms 轮询后处理。

---

## 参考

- **架构文档**: `/llmdoc/architecture/file-watcher.md` - 深入理解防抖、事件流、线程模型
- **源代码**:
  - `src/fs/watcher.rs` - FileWatcher 和 Debouncer 实现
  - `src/fs/mod.rs` (314-360) - watcher_loop 实现
  - `src/fs/index.rs` - FileIndex 增量更新方法

