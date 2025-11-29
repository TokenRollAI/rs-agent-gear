# 内存索引系统架构（FileIndex）

## 1. 核心定义

**什么是 FileIndex：** 一个线程安全的内存文件索引系统，通过 DashMap 无锁并发数据结构和原子标志，实现快速文件查询、Glob 模式匹配和增量更新。

**主要用途：** 将文件系统状态快照保存在内存中，支持毫秒级的文件列表和路径查询，为搜索引擎提供预过滤和索引加速。

## 2. 核心数据结构

### 主结构体

`src/fs/index.rs:48-66` (FileIndex)：
- **entries** (`DashMap<PathBuf, FileMetadata>`): 全量元数据映射，每个文件/目录映射到其大小、修改时间、类型和二进制标志
- **dir_children** (`DashMap<PathBuf, Vec<PathBuf>>`): 目录孩子缓存，支持快速目录遍历
- **all_files** (`RwLock<Vec<PathBuf>>`): 所有文件路径的线性列表，用于快速迭代和 **/* 查询
- **is_ready** (`AtomicBool`): 索引完成标志，查询前检查此标志以避免读未初始化数据
- **is_building** (`AtomicBool`): 构建进行中标志，使用 CAS 确保只有一个构建进程

### FileMetadata 元数据

`src/fs/index.rs:19-35` (FileMetadata)：
- **size** (u64): 文件字节数
- **mtime** (f64): Unix 时间戳（秒），支持小数秒精度
- **is_dir** (bool): 是否目录标志
- **is_binary** (bool): 二进制文件检测标志，用于搜索时跳过二进制文件

## 3. 索引构建流程

### 并发控制

`src/fs/index.rs:82-90` (build 方法入口)：
使用 `compare_exchange(false, true)` 原子操作确保在任何时刻只有一个线程执行构建。失败表示已有构建进程在运行，立即返回。

### 目录扫描

`src/fs/index.rs:100-105`：
- 使用 `ignore::WalkBuilder::build_parallel()` 并行遍历目录
- 自动尊重 `.gitignore`、`.git/info/exclude` 和全局 gitignore
- `hidden(false)` 包含隐藏文件，`git_ignore(true)` 启用过滤
- 并行扫描减少初始化延迟

### 二进制检测

`src/fs/index.rs:131-136`：
- 对每个非目录文件，读取前 512 字节检查 null 字节
- `buffer[..n].contains(&0)` 存在 null 即视为二进制
- 检测结果存储在 FileMetadata，用于搜索时跳过

### 数据映射

`src/fs/index.rs:145-160`：
- 每个文件/目录插入 entries DashMap，路径为 key
- 维护 dir_children 映射，每个父目录追踪孩子列表
- 仅文件（非目录）添加到 all_files 列表

### 原子完成标记

`src/fs/index.rs:172-173`：
- 设置 `is_ready = true` (SeqCst 顺序语义)
- 设置 `is_building = false` (SeqCst)
- 确保所有构建线程的写操作对查询线程可见

## 4. 并发模型

### 无锁读操作

- **entries**: DashMap 支持多个读者无锁并发访问（细粒度分桶）
- **all_files**: RwLock 允许多个读者共存，仅写操作排他
- 搜索引擎可在构建期间进行查询（读取部分完成的索引）

### 原子标志同步

- **is_ready**: 查询前检查，采用 SeqCst 保证顺序可见性
- **is_building**: CAS 操作确保单一构建进程，失败时无需重试

### 线程共享模式

```
Main Thread → Arc<FileIndex> ← Index Build Thread
                              ← Watcher Update Thread
```

通过 Arc 共享，Index Build 线程构建完成后，Watcher 线程可以执行增量更新。

## 5. 快速路径优化

### **/* 特殊处理

`src/fs/index.rs:211-225`：
- 模式为 "**/*" 或 "**" 时跳过 Glob 编译
- 直接返回 all_files 列表的克隆或 entries 迭代
- 减少单一文件列表查询的开销（避免正则匹配）

### 相对路径优化

`src/fs/index.rs:307-320` (relative_path_fast)：
- 内联方法，尽量避免不必要的字符串分配
- 快速路径：`path.strip_prefix(&root)` + `to_str()` 一次拷贝
- 备选路径：使用 `to_string_lossy()` 处理非 UTF-8 路径

### 并行过滤

`src/fs/index.rs:222-238`：
- Glob 匹配时使用 `Rayon::par_iter()` 并行化
- 每个工作线程独立检查文件是否匹配模式
- 充分利用多核加速大规模文件列表的过滤

## 6. 查询接口

### list / glob 查询

`src/fs/index.rs:203-267`：
```
入口: list(pattern, only_files=true)
  ├─ is_ready() 检查
  ├─ 快速路径: pattern == "**/*" → all_files
  ├─ 常规路径: compile_glob(pattern) → par_iter + filter
  └─ 返回: Vec<String> 相对路径列表
```

- **only_files=true**: 仅返回文件（非目录）
- **only_files=false**: 返回所有条目（文件+目录）

### get_metadata 查询

`src/fs/index.rs:301-304`：
- O(1) 哈希表查询，无锁访问 DashMap
- 返回 FileMetadata 克隆（包含大小、修改时间、类型、二进制标志）

### glob_paths 查询

`src/fs/index.rs:269-299`：
- 返回 Vec<PathBuf> 版本，供搜索引擎内部使用
- 避免字符串转换开销，直接操作路径对象

## 7. 增量更新接口

### add_path

`src/fs/index.rs:353-405`：
```
操作: 文件创建事件
  ├─ 获取完整元数据 (size, mtime, is_binary)
  ├─ 插入 entries DashMap
  ├─ 更新 dir_children 缓存
  └─ 追加到 all_files 列表 (仅文件)
```

- 检查文件存在性，不存在则忽略
- 避免重复添加到 all_files（检查 contains）

### update_path

`src/fs/index.rs:407-442`：
```
操作: 文件修改事件
  ├─ 获取更新后的元数据
  ├─ 更新 entries 中的元数据
  └─ 不修改 dir_children 或 all_files 列表
```

- 仅更新 FileMetadata（大小、修改时间、二进制标志可能变化）
- 路径本身不变

### remove_path

`src/fs/index.rs:444-449`：
```
操作: 文件删除事件
  ├─ 从 entries 移除
  ├─ 从 dir_children 更新（移除孩子记录）
  └─ 从 all_files 过滤移除
```

- 从三个数据结构中一致性移除
- 不涉及元数据获取，仅操作内存结构

## 8. 并发安全保证

### DashMap 特性

- 细粒度分桶锁，多个线程可并发访问不同桶
- entries、dir_children 均采用此模式
- 插入、查询、删除都支持无锁读并发

### RwLock<Vec> 特性

- all_files 的读操作可并发（多个查询线程）
- 写操作（构建、增量更新）排他，但不阻止读取
- 使用 read()/write() 防止死锁

### 原子操作内存顺序

- **is_ready.store(true, SeqCst)**: 完全同步屏障，保证之前的构建结果对所有线程可见
- **is_building.compare_exchange()**: CAS 操作隐含 SeqCst 语义

### 竞争条件处理

- **查询过程中文件被删除**: 索引返回过期路径，搜索引擎会捕获文件读取错误
- **构建过程中文件被监听更新**: DashMap 允许并发，增量更新会覆盖旧数据
- **多个增量更新**: dir_children 和 all_files 写操作序列化（RwLock）

## 9. 二进制文件检测机制

### 检测算法

`src/fs/index.rs:178-190`：
```rust
fn is_binary_file(path: &Path) -> bool {
    if let Ok(mut file) = std::fs::File::open(path) {
        let mut buffer = [0u8; 512];
        if let Ok(n) = file.read(&mut buffer) {
            return buffer[..n].contains(&0);  // 存在 null 字节
        }
    }
    false
}
```

- 采样前 512 字节，检查是否存在 null 字节（0x00）
- null 字节是二进制文件常见特征（文本文件通常不含）
- 检测失败默认返回 false（视为文本文件）

### 检测时机

- **构建阶段**: 扫描所有文件时逐个检测并存储标志
- **增量更新**: add_path 和 update_path 再次检测，确保最新状态

### 搜索集成

`src/fs/searcher.rs` 中的 collect_files 会调用 is_binary_file，搜索前跳过二进制文件。

## 10. 性能特征

| 操作 | 时间复杂度 | 说明 |
|------|----------|------|
| 构建 (10000 文件) | O(n) | 线性扫描 + DashMap 插入，并行扫描减少延迟 |
| 快速路径 (list **/*) | O(n) | 线性读 all_files，Rayon 并行化 |
| Glob 查询 | O(n) | n 文件数，Glob 编译 O(1)，并行过滤 O(n/p) |
| get_metadata | O(1) | 哈希表查询 |
| add_path | O(1) | DashMap 插入 + RwLock 追加 |
| update_path | O(1) | DashMap 更新 |
| remove_path | O(n) | 需要线性扫描 all_files 过滤 |

## 11. 与监听系统的集成

`src/fs/mod.rs:428-440` (watcher_loop 中的使用)：
```
文件监听事件 ──────► handle_event() ──► 分类
                                       ├─ Created → index.add_path()
                                       ├─ Modified → index.update_path()
                                       ├─ Deleted → index.remove_path()
                                       └─ Renamed → remove + add
```

监听线程通过事件驱动触发增量更新，保持索引与文件系统同步。

---

**主要源文件：**
- `src/fs/index.rs:1-500` - 完整索引实现
- `src/fs/mod.rs:428-440` - 监听集成
- `src/fs/searcher.rs` - 搜索引擎使用索引
