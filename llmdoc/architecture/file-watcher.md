# 文件监听系统架构

## 1. 身份

- **定义**: 一个跨平台的实时文件系统变动检测和防抖系统，自动保持内存索引与磁盘文件状态同步。
- **目的**: 通过后台监听线程持续捕获文件创建、修改、删除、重命名等事件，在防抖后触发索引的增量更新，实现零延迟的索引同步。

## 2. 核心组件

- `src/fs/watcher.rs:19-30` (ChangeKind): 文件变动事件的四种类型，包含创建、修改、删除和重命名。
- `src/fs/watcher.rs:33-41` (FileChange): 防抖后的文件变动事件结构，包含路径、变动类型和时间戳。
- `src/fs/watcher.rs:43-127` (Debouncer): 事件防抖器，在 100ms 时间窗口内收集和合并高频事件。
- `src/fs/watcher.rs:129-232` (FileWatcher): 跨平台文件监听器，基于 notify crate，支持 inotify/FSEvents/ReadDirectoryChangesW。
- `src/fs/mod.rs:314-360` (FileSystem::watcher_loop): 后台监听循环，处理防抖事件并调用索引增量更新方法。

## 3. 执行流程 (LLM 检索地图)

### 3.1 系统初始化

1. **FileSystem 构造**（`src/fs/mod.rs:49-104`）：
   - 用户调用 `FileSystem::new(root, auto_watch=true)`
   - 验证根目录存在且为目录
   - 创建 `Arc<FileIndex>` 和启动后台索引线程

2. **FileWatcher 创建**（`src/fs/mod.rs:73-94`）：
   - 如果 `auto_watch=true`，创建 `FileWatcher::new(root_path, Duration::from_millis(100))`
   - 初始化 notify 底层监听器，设置 100ms 轮询间隔
   - 递归监听根目录（`RecursiveMode::Recursive`）

3. **监听线程启动**（`src/fs/mod.rs:81-83`）：
   - 在独立线程中运行 `FileSystem::watcher_loop()`
   - 持有 `Arc<FileWatcher>`, `Arc<FileIndex>`, `Arc<AtomicBool>` 的克隆

### 3.2 事件检测和防抖流程

1. **原始事件捕获**（`src/fs/watcher.rs:174-184`）：
   - `watcher.process_events()` 通过 crossbeam channel 读取所有待处理事件
   - 对每个 notify 事件调用 `handle_event()`

2. **事件类型映射**（`src/fs/watcher.rs:186-216`）：
   - `EventKind::Create(File|Folder|Any)` → `ChangeKind::Created`
   - `EventKind::Modify(Data(...))` → `ChangeKind::Modified`
   - `EventKind::Modify(Name(Both))` → `ChangeKind::Renamed { from, to }`
   - `EventKind::Remove(File|Folder|Any)` → `ChangeKind::Deleted`
   - 其他事件类型被忽略

3. **防抖合并规则**（`src/fs/watcher.rs:62-84`）：
   - 事件添加到 Debouncer 的 HashMap（按路径映射）
   - **合并规则 1**: `Created + Deleted` = 移除（文件最终未创建）
   - **合并规则 2**: `Created + Modified` = 保持 `Created`（忽略修改）
   - **其他情况**: 后续事件覆盖前序事件

4. **防抖刷新**（`src/fs/watcher.rs:86-108`）：
   - `debouncer.flush()` 检查所有待处理事件的时间戳
   - 如果事件已稳定 ≥100ms，返回该事件并从映射移除
   - 未稳定的事件继续等待下一次刷新

### 3.3 索引增量更新

1. **监听循环处理**（`src/fs/mod.rs:326-355`）：
   - 每 50ms 轮询一次（`std::thread::sleep(Duration::from_millis(50))`)
   - 调用 `watcher.process_events()` 获取所有防抖稳定的事件

2. **事件分发到索引**（`src/fs/mod.rs:329-354`）：
   - `ChangeKind::Created` → `index.add_path(&event.path)`
   - `ChangeKind::Modified` → `index.update_path(&event.path)`
   - `ChangeKind::Deleted` → `index.remove_path(&event.path)`
   - `ChangeKind::Renamed { from, to }` → `index.remove_path(&from)` + `index.add_path(&to)`

3. **索引操作**（`src/fs/index.rs`）：
   - `add_path()`: 读取文件元数据，插入 entries DashMap，更新 dir_children 和 all_files
   - `update_path()`: 重新读取文件元数据，更新 entries 中的条目
   - `remove_path()`: 从三个映射中删除路径

### 3.4 停止和清理

1. **关闭信号**（`src/fs/mod.rs:261-269`）：
   - `FileSystem::close()` 调用时，设置 `stop_flag` 为 true
   - 调用 `watcher.stop()` 设置运行标志为 false

2. **监听线程退出**（`src/fs/mod.rs:322-324`）：
   - 下一次 watcher_loop 轮询时读取 `stop_flag.load()`
   - 如果为 true，跳出循环并线程结束

3. **资源清理**：
   - FileWatcher Drop trait 自动调用 `stop()`
   - crossbeam channel 自动释放
   - Debouncer HashMap 被丢弃

## 4. 跨平台实现细节

### 4.1 notify 集成

notify crate 根据操作系统自动选择最优实现：

- **Linux**: inotify 系统调用
  - 支持 IN_CREATE, IN_MODIFY, IN_DELETE, IN_MOVED_FROM/IN_MOVED_TO 等事件
  - 需要通过 `/proc/sys/fs/inotify/max_user_watches` 配置监听限制

- **macOS**: FSEvents API
  - 粗粒度批量事件，延迟约 1 秒
  - 自动合并快速连续的文件系统变动

- **Windows**: ReadDirectoryChangesW API
  - 异步高效实现
  - 支持整个目录树的监听

### 4.2 轮询配置

`src/fs/watcher.rs:149-154`：
```rust
Config::default().with_poll_interval(Duration::from_millis(100))
```

轮询间隔 100ms 平衡了反应速度和 CPU 开销。

## 5. 并发和线程安全

### 5.1 线程模型

```
Main Thread (Python)
    ├─ create FileSystem
    └─ call methods

Index Thread (Background)
    └─ FileIndex::build() - 一次性执行

Watcher Thread (Background)
    └─ FileSystem::watcher_loop()
        └─ process_events() + index 更新
```

### 5.2 同步原语

- **Arc<FileIndex>**: 三个线程间共享索引读访问
- **Arc<FileWatcher>**: 主线程创建，监听线程消费事件
- **Arc<AtomicBool> stop_flag**: 控制监听线程退出，无锁原子操作
- **RwLock<Debouncer>**: 单个写锁保护防抖器的 HashMap
- **crossbeam::channel**: Receiver 在监听线程独占读取

### 5.3 竞争条件处理

1. **索引和监听的同步**：
   - 索引构建线程独立运行，使用 CAS 操作确保单个构建进程
   - 监听线程通过调用 `add_path()` 等方法进行增量更新
   - FileIndex 使用 DashMap 无锁并发设计，允许多读并发

2. **事件丢失预防**：
   - notify 内部使用缓冲队列（crossbeam channel）
   - Debouncer 防止短时间内重复事件
   - 50ms 轮询间隔确保及时处理

3. **内存顺序**：
   - `stop_flag.load/store(Ordering::SeqCst)`: 完全同步屏障，确保可见性

## 6. 设计权衡

### 6.1 防抖窗口 100ms

**优势**：
- 减少高频事件（如批量保存文件）对索引的冲击
- 合并相关事件（如创建+修改 → 单次创建）

**权衡**：
- 事件延迟 ≤100ms（应用层无感知）
- 快速连续操作会被合并（大多数场景这是期望的）

### 6.2 后台线程模型

**优势**：
- 不阻塞主 Python 线程
- GIL 不受影响
- 索引更新和文件监听并行进行

**权衡**：
- 最终一致性：索引和磁盘有短暂延迟
- 多线程调试复杂度增加

### 6.3 事件合并规则

**Created + Deleted = 无事件**：
- 避免创建临时文件导致的虚假索引操作
- 减少索引不必要的更新

**Created + Modified = 保持 Created**：
- 文件刚创建的修改通常无关紧要
- 减少不必要的 add + update 序列

## 7. Python API 集成

### 7.1 生命周期控制

`src/fs/mod.rs:42-49`：
```rust
#[new]
#[pyo3(signature = (root, auto_watch = true))]
pub fn new(root: String, auto_watch: bool) -> PyResult<Self>
```

- `auto_watch=true`（默认）：启动监听线程，索引自动同步
- `auto_watch=false`：仅构建索引，需手动调用 `refresh()`

### 7.2 状态查询

- `is_watching()`: 检查监听是否活跃
- `is_ready()`: 检查索引构建完成状态
- `pending_changes()`: 处理并返回待处理事件计数

### 7.3 上下文管理器支持

`src/fs/mod.rs:287-300`：
```rust
fn __enter__() -> Self { ... }
fn __exit__() { self.close(); ... }
```

Python 用法：
```python
with FileSystem("/path") as fs:
    fs.list("**/*.py")
# 自动调用 close()，停止监听线程
```

## 8. 性能特性

- **事件防抖**: 100ms 时间窗口，减少索引更新频率至 10Hz
- **增量更新**: 仅更新变动文件，避免全扫描
- **后台处理**: 50ms 轮询周期，低 CPU 开销（< 1% 单核）
- **缓冲队列**: crossbeam channel 自动缓冲，防止事件丢失

