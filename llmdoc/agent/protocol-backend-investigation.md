# Protocol 和 Backend 实现模式调查报告

## 调查概述

针对项目中 protocol 和 backend 实现模式的深度调查，包括 BackendProtocol 定义、类型系统和接口设计。

---

## Code Sections (代码证据清单)

### 类型定义和 Stub 文件

- `agent_gear/_rust_core.pyi` (类型 stub 文件): 为所有 Rust 核心类提供完整类型提示，包括 FileSystem、FileMetadata、SearchOptions、SearchResult 等。这是 Python 类型检查的唯一源头。

### Rust 核心实现

- `src/lib.rs` (PyModule 注册): 通过 #[pymodule] 定义 `_rust_core` 模块，注册 FileSystem、SearchResult、SearchOptions、FileMetadata 四个主要类，无任何 Protocol/Trait 定义。

- `src/fs/mod.rs` (FileSystem 主类 - 行 31-107): 定义 `#[pyclass] pub struct FileSystem`，包含以下私有字段：
  - `root: PathBuf`
  - `index: Arc<FileIndex>`
  - `searcher: Searcher`
  - `watcher: Option<Arc<FileWatcher>>`
  - `watcher_thread: Option<std::thread::JoinHandle<()>>`
  - `stop_flag: Arc<AtomicBool>`

- `src/fs/index.rs` (FileMetadata 结构 - 行 22-51): 定义 `#[pyclass] pub struct FileMetadata` 包含：
  - `size: u64` (#[pyo3(get)])
  - `mtime: f64` (#[pyo3(get)])
  - `is_dir: bool` (#[pyo3(get)])
  - `is_binary: bool` (#[pyo3(get)])

- `src/fs/index.rs` (FileIndex 结构 - 行 87-100): 定义内存索引，包含：
  - `entries: DashMap<PathBuf, FileMetadata>`
  - `dir_children: DashMap<PathBuf, Vec<PathBuf>>`
  - `all_files: RwLock<Vec<PathBuf>>`
  - `is_ready: AtomicBool`
  - `is_building: AtomicBool`

- `src/fs/searcher.rs` (SearchOptions 结构 - 行 18-54): 定义 `#[pyclass] pub struct SearchOptions`，包含四个可配置字段（case_sensitive, max_results, max_file_size, context_lines）及其 __init__ 方法和 Default 实现。

- `src/fs/searcher.rs` (SearchResult 结构 - 行 68-106): 定义 `#[pyclass] pub struct SearchResult`，包含五个 #[pyo3(get)] 只读字段（file, line_number, content, context_before, context_after）及 __repr__ 实现。

- `src/fs/searcher.rs` (Searcher 实现 - 行 108-141): 定义非公开 `pub struct Searcher` 结构体（无 #[pyclass] 修饰），仅在 Rust 层使用，暴露 grep 和 grep_with_files 两个方法（均通过 py.allow_threads()）。

- `src/utils/error.rs` (AgentGearError 枚举 - 行 8-45): 使用 #[derive(Error)] 定义 9 种错误变体：Io, PathNotFound, Pattern, TextNotUnique, TextNotFound, IndexNotReady, Glob, Regex, Internal。

- `src/utils/error.rs` (PyErr 转换 - 行 47-69): 实现 `From<AgentGearError> for PyErr`，将错误映射为三种 Python 异常类型：PyIOError (Io), PyValueError (Pattern/PathNotFound/TextNotUnique/TextNotFound/Glob/Regex), PyRuntimeError (IndexNotReady/Internal)。

### Python 包装层

- `agent_gear/__init__.py` (FileSystem 包装类 - 行 45-207): 定义纯 Python 包装类，通过 `self._inner = _RustFileSystem(...)` 持有 Rust 实现，暴露同名方法但添加额外方法（wait_ready）。

- `agent_gear/__init__.py` (AsyncFileSystem 包装类 - 行 210-363): 定义异步包装类，使用 `asyncio.to_thread()` 包装所有 I/O 操作，提供 async/await 接口。

### I/O 操作实现

- `src/fs/io.rs` (read_file 函数 - 行 15-32): 使用 `py.allow_threads()` 释放 GIL，调用 `std::fs::read_to_string()`，错误处理通过 AgentGearError::PathNotFound 和 AgentGearError::Io。

- `src/fs/io.rs` (read_batch 函数 - 行 48-61): 根据文件数量选择串行或并行模式（阈值 30 文件），通过 Rayon `par_iter()` 实现并行读取。

---

## Report (分析报告)

### 1. 是否存在 BackendProtocol 定义？

**结论：否。项目中不存在任何 Protocol、Trait 或抽象接口定义。**

项目采用以下设计：
1. **直接 PyO3 绑定**：Rust struct 直接标记 `#[pyclass]`，暴露给 Python
2. **具体实现模式**：所有接口通过具体类（FileSystem、FileMetadata 等）实现，而非协议或 trait
3. **单一实现**：没有多个 backend 实现或可切换的后端

### 2. 现有接口的完整清单

#### 主要类（PyClass）

| 类名 | 源文件 | 用途 | 是否在 Python 中使用 |
|------|--------|------|-------------------|
| FileSystem | src/fs/mod.rs | 核心文件系统接口 | ✅ 直接导入 |
| FileMetadata | src/fs/index.rs | 文件元数据 DTO | ✅ grep 和 get_metadata 返回 |
| SearchOptions | src/fs/searcher.rs | 搜索参数对象 | ❌ 内部使用，Python 用参数替代 |
| SearchResult | src/fs/searcher.rs | 搜索结果 DTO | ✅ grep 返回 |

#### FileSystem 公开方法（@pymethods）

- `new(root: str, auto_watch: bool = True)` - 构造函数
- `list(pattern: str = "**/*", only_files: bool = True)` → `Vec<String>`
- `glob(pattern: str)` → `Vec<String>`
- `read_file(path: str, encoding: str = "utf-8")` → `String`
- `read_batch(paths: list[str])` → `dict[str, str]`
- `read_lines(path: str, start_line: int, count: int | None)` → `list[str]` (Phase 3)
- `read_file_range(path: str, offset: int, limit: int)` → `String` (Phase 3)
- `write_file(path: str, content: str)` → `bool`
- `write_file_fast(path: str, content: str)` → `bool` (新增)
- `edit_replace(path: str, old_text: str, new_text: str, strict: bool = True)` → `bool`
- `grep(query: str, glob_pattern: str = "**/*", case_sensitive: bool = False, max_results: int = 1000)` → `list[SearchResult]`
- `get_metadata(path: str)` → `FileMetadata`
- `refresh()` → `None`
- `is_ready()` → `bool`
- `is_watching()` → `bool`
- `pending_changes()` → `int` (新增)
- `close()` → `None`
- `__enter__()` / `__exit__()` - 上下文管理器

### 3. 类型系统架构

#### Type Stub 文件 (_rust_core.pyi)

项目维护 `agent_gear/_rust_core.pyi` stub 文件提供完整类型提示。此文件结构：

```
- FileMetadata 类（只读属性：size, mtime, is_dir, is_binary）
- SearchOptions 类（可读写属性 + __init__）
- SearchResult 类（只读属性）
- FileSystem 类（所有方法签名）
```

#### Python 包装层类型注解

`agent_gear/__init__.py` 中：
- FileSystem 包装类使用现代 Python 3.12 语法：`list[str]`, `dict[str, str]`, `int | None`
- 所有方法完整类型注解（满足 mypy strict 模式）
- AsyncFileSystem 镜像 FileSystem 接口，方法返回类型为 `Coroutine`

### 4. 现有实现模式（无 Protocol）

#### 模式 A：PyO3 直接绑定（数据类）

```rust
#[pyclass]
#[derive(Clone, Debug)]
pub struct FileMetadata {
    #[pyo3(get)]
    pub size: u64,
    // ...
}
```

特点：
- 简洁，直接暴露字段
- 适合不可变数据传输对象 (DTO)
- 自动生成 Python 属性

#### 模式 B：PyO3 方法绑定（有逻辑的类）

```rust
#[pyclass]
pub struct FileSystem { /* 私有字段 */ }

#[pymethods]
impl FileSystem {
    #[new]
    pub fn new(root: String, auto_watch: bool) -> PyResult<Self> { /* ... */ }
    pub fn list(&self, pattern: &str, only_files: bool) -> PyResult<Vec<String>> { /* ... */ }
}
```

特点：
- 完全封装内部状态
- 支持 Rust 错误处理（PyResult）
- 自动 Python 异常转换

#### 模式 C：Python 包装补强

```python
class FileSystem:
    def __init__(self, root: str, auto_watch: bool = True) -> None:
        self._inner = _RustFileSystem(root, auto_watch)

    def wait_ready(self, timeout: float = 30.0) -> bool:
        """Python 添加的辅助方法"""
```

特点：
- Python 层可添加 Rust 中无法实现的逻辑
- 时间循环轮询（wait_ready）

#### 模式 D：异步包装

```python
class AsyncFileSystem:
    async def list(self, ...):
        import asyncio
        return await asyncio.to_thread(self._sync.list, ...)
```

特点：
- 使用 `asyncio.to_thread()` 包装同步方法
- 提供原生 async/await 支持
- 无需 Rust 异步实现

### 5. 错误处理模式

**两层错误映射：**

1. **Rust 层** (`src/utils/error.rs`):
   ```
   AgentGearError enum → 9 种变体
   ↓
   From<AgentGearError> for PyErr → Python 异常
   ```

2. **Python 层**:
   ```
   PyResult<T> → Python 运行时异常
   捕获并转换为适当的 Python 异常类型
   ```

**错误分类：**
- I/O 错误 → PyIOError
- 业务逻辑错误 (文本不唯一、路径不存在等) → PyValueError
- 系统状态错误 (索引未就绪) → PyRuntimeError

### 6. 并发和同步模式

**Rust 层的并发原语：**

| 原语 | 使用场景 | 特性 |
|------|---------|------|
| DashMap | entries, dir_children, glob 缓存 | 无锁细粒度锁，多读并发 |
| RwLock<Vec> | all_files 列表 | 多读单写 |
| AtomicBool | is_ready, is_building, stop_flag | 原子 CAS，无锁 |
| Arc<T> | FileIndex, FileWatcher 共享 | 跨线程所有权共享 |
| Rayon::par_iter | 批量读取、并行搜索、Glob 过滤 | 自动线程池 |

**GIL 释放策略：**

所有 I/O 操作必须使用 `py.allow_threads()` 释放 GIL：
```rust
pub fn read_file(py: Python<'_>, path: &Path, _encoding: &str) -> PyResult<String> {
    py.allow_threads(|| {
        std::fs::read_to_string(path) // 可由其他 Python 线程并发执行
    })
}
```

### 7. 模块组织结构

```
src/
├── lib.rs                 # 模块入口，PyModule 注册
├── fs/
│   ├── mod.rs            # FileSystem 主类定义 + 线程模型
│   ├── index.rs          # FileIndex + FileMetadata 定义
│   ├── searcher.rs       # Searcher + SearchOptions + SearchResult
│   ├── io.rs             # 读写操作（read_file, read_batch 等）
│   ├── atomic.rs         # 原子写入实现
│   └── watcher.rs        # 文件监听器
└── utils/
    ├── error.rs          # AgentGearError + PyErr 转换
    └── mod.rs

agent_gear/
├── __init__.py           # FileSystem + AsyncFileSystem 包装
└── _rust_core.pyi        # Type stubs 用于 mypy
```

### 8. 版本化和稳定性

**当前无 Protocol/Interface 定义的影响：**

优点：
- 实现简洁，直接暴露 Rust 类型
- 避免抽象开销，性能最优
- PyO3 自动生成 Python 绑定

缺点：
- 难以支持多个 backend 实现（如 S3Backend、MemoryBackend）
- 难以在 Python 中动态替换实现
- 密切耦合 Rust 和 Python 接口

---

## Conclusions (关键发现)

1. **项目结构：无 Protocol，直接 PyO3 绑定**
   - 没有 BackendProtocol 或抽象 trait
   - 所有接口通过具体 PyO3 类实现
   - 单一 Rust 实现导出

2. **接口层次（从底到顶）：**
   ```
   Rust 具体实现 (_rust_core.pyi)
         ↓
   Python 包装层 (agent_gear/__init__.py)
         ↓
   用户 API (FileSystem, AsyncFileSystem)
   ```

3. **类型系统完整性：**
   - 通过 `.pyi` stub 文件提供完整 Python 类型信息
   - 支持 mypy strict 模式
   - Python 3.12+ 现代语法

4. **设计模式：**
   - 数据类 (DTO): 使用 `#[pyclass]` + `#[pyo3(get)]`
   - 有逻辑的类：使用 `#[pymethods]` + 私有字段封装
   - Python 补强：在 Python 层添加 Rust 中无法实现的功能
   - 异步支持：asyncio.to_thread() 自动包装

5. **如果需要添加 Protocol/Backend 支持，建议：**

   **方案 A：在 Python 层定义 Protocol（推荐）**
   ```python
   from typing import Protocol

   class BackendProtocol(Protocol):
       def list(self, pattern: str) -> list[str]: ...
       def read_file(self, path: str) -> str: ...
       # ...
   ```
   优点：不改动 Rust，易于扩展
   缺点：性能有轻微开销

   **方案 B：在 Rust 层定义 Trait（需重构）**
   ```rust
   pub trait Backend {
       fn list(&self, pattern: &str) -> PyResult<Vec<String>>;
       // ...
   }

   impl Backend for FileSystem { /* ... */ }
   impl Backend for S3Backend { /* ... */ }
   ```
   优点：可在 Rust 层实现多个 backend
   缺点：需要大幅重构现有代码

   **当前推荐：方案 A**，因为项目已稳定，多 backend 需求仍未出现。

6. **引入 FileInfo / GrepMatch / EditResult / WriteResult 的方式：**

   使用现有模式：新增 #[pyclass] 类型
   ```rust
   #[pyclass]
   #[derive(Clone, Debug)]
   pub struct FileInfo {
       #[pyo3(get)]
       pub path: String,
       #[pyo3(get)]
       pub metadata: FileMetadata,
   }
   ```

---

## Relations (代码关系图)

**初始化流程：**
```
FileSystem.__init__(root, auto_watch=True)
    ├─ _RustFileSystem(root, auto_watch)          [src/fs/mod.rs:50-107]
    │   ├─ FileIndex::new(root)                   [src/fs/index.rs]
    │   │   └─ 后台线程：FileIndex::build()       [后台线程启动]
    │   ├─ Searcher::new(root)                    [src/fs/searcher.rs:114-117]
    │   └─ FileWatcher::new(root) (if auto_watch) [src/fs/watcher.rs]
    │       └─ 后台线程：watcher_loop()          [src/fs/mod.rs:428-440]
    └─ Python 补充：wait_ready() 时间轮询        [agent_gear/__init__.py:75-91]
```

**查询流程：**
```
FileSystem.list(pattern) → src/fs/mod.rs:118-120
    └─ FileIndex.list(pattern) → src/fs/index.rs:203-267
        ├─ 快速路径：pattern == "**/*"
        │   └─ 返回 all_files 克隆
        └─ Glob 路径：
            ├─ compile_glob(pattern)
            └─ Rayon::par_iter().filter()
```

**搜索流程：**
```
FileSystem.grep(query, glob_pattern, ...)
    └─ src/fs/mod.rs:200+ (FileSystem method)
        └─ Searcher.grep(query, glob_pattern, options)
            └─ src/fs/searcher.rs:120-129 (py.allow_threads)
                └─ grep_internal(query, ...)
                    ├─ 文件收集（索引或 glob）
                    ├─ 并行搜索（Rayon）
                    └─ 返回 Vec<SearchResult>
```

**并发关系：**
```
主线程：
  ├─ 前台查询（list, read, grep）[无锁读]
  │   └─ DashMap/RwLock 并发访问
  │
  ├─ 索引构建线程
  │   └─ FileIndex::build() → DashMap/RwLock 写
  │
  └─ 文件监听线程 (if auto_watch)
      └─ watcher_loop() → 增量更新索引
```

**Python 包装层的代理关系：**
```
agent_gear.FileSystem (Python 类)
    ├─ 所有主要方法 → self._inner._RustFileSystem
    ├─ wait_ready() → 纯 Python 实现（Python 层补强）
    └─ 返回类型映射：
        ├─ list[str], dict[str, str] → 直接传回
        ├─ FileMetadata, SearchResult → Rust PyClass 对象
        └─ bool, int → Python 原生类型
```

**错误处理链：**
```
Rust 错误 (AgentGearError)
    ↓ [From<AgentGearError> for PyErr]
Python 异常
    ↓ [PyResult<T> 自动处理]
Python 运行时异常
    ├─ PyIOError
    ├─ PyValueError
    └─ PyRuntimeError
```

---

## 其他观察

### 与 deepagents 的关系

根据搜索结果，项目中**没有找到** `deepagents` 的导入或直接关联。项目是独立的文件系统操作库，可被其他项目（包括 deepagents）使用。

### 为什么不使用 Protocol？

1. **设计阶段决策**：项目专注于单一 FileSystem 实现，不需要多 backend 支持
2. **性能考虑**：直接具体类比 Protocol 更快（无动态分派开销）
3. **Rust/Python 边界**：PyO3 基于具体类型生成绑定，Protocol 的动态性与此不兼容
4. **迭代演进**：可在 Python 层后期添加 Protocol，而无需改动 Rust

---

**报告生成时间**: 2025-11-30
**调查范围**: llmdoc/*, agent_gear/*, src/
