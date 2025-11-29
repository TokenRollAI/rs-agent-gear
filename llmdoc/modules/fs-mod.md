# fs 模块详解

## 模块概述

`fs` 模块是 Agent-Gear 的核心模块，提供高性能文件系统操作。

位置：`src/fs/`

## 子模块

### mod.rs - FileSystem 类

主入口，定义 `#[pyclass] FileSystem`。

**关键方法：**

| 方法 | 描述 | 关键点 |
|------|------|--------|
| `new` | 创建实例 | 启动后台索引线程 |
| `list` | 列出文件 | 从内存索引查询 |
| `glob` | Glob 匹配 | 支持 `**` 递归 |
| `read_file` | 读取单文件 | 释放 GIL |
| `read_batch` | 批量读取 | Rayon 并行 |
| `write_file` | 原子写入 | temp→fsync→rename |
| `edit_replace` | 文本替换 | 支持 strict 模式 |
| `grep` | 内容搜索 | 多线程并行 |

### io.rs - I/O 操作

**函数：**

```rust
pub fn read_file(py: Python<'_>, path: &Path, encoding: &str) -> PyResult<String>
pub fn read_batch(py: Python<'_>, paths: &[PathBuf]) -> PyResult<HashMap<String, String>>
pub fn write_file(py: Python<'_>, path: &Path, content: &str) -> PyResult<()>
pub fn edit_replace(py: Python<'_>, path: &Path, old: &str, new: &str, strict: bool) -> PyResult<bool>
```

**关键点：**

- 所有函数使用 `py.allow_threads()` 释放 GIL
- `read_batch` 使用 `Rayon::par_iter()` 并行读取
- `edit_replace` 在 strict 模式下检查唯一性

### index.rs - 内存索引

**数据结构：**

```rust
pub struct FileIndex {
    root: PathBuf,
    entries: DashMap<PathBuf, FileMetadata>,
    dir_children: DashMap<PathBuf, Vec<PathBuf>>,
    all_files: RwLock<Vec<PathBuf>>,
    is_ready: AtomicBool,
    is_building: AtomicBool,
}

pub struct FileMetadata {
    pub size: u64,
    pub mtime: f64,
    pub is_dir: bool,
    pub is_binary: bool,
}
```

**关键点：**

- 使用 `ignore` crate 并行扫描目录
- 自动跳过 `.gitignore` 中的文件
- 二进制文件检测：读取前 512 字节检查 null 字符

### searcher.rs - 搜索引擎

**数据结构：**

```rust
pub struct SearchOptions {
    pub case_sensitive: bool,
    pub max_results: usize,
    pub max_file_size: u64,
    pub context_lines: usize,
}

pub struct SearchResult {
    pub file: String,
    pub line_number: u32,
    pub content: String,
    pub context_before: Vec<String>,
    pub context_after: Vec<String>,
}
```

**关键点：**

- 使用 `regex` crate 进行正则匹配
- Rayon 并行搜索多个文件
- 在 Rust 层截断结果，避免大量数据传回 Python
- 自动跳过二进制文件

### atomic.rs - 原子写入

**函数：**

```rust
pub fn atomic_write(path: &Path, content: &[u8]) -> Result<()>
```

**实现模式：**

1. 在目标目录创建临时文件（确保同文件系统）
2. 写入内容
3. `fsync()` 刷新到磁盘
4. `rename()` 原子替换

## 错误处理

所有错误定义在 `utils/error.rs`：

```rust
pub enum AgentGearError {
    Io(std::io::Error),
    PathNotFound(String),
    Pattern(String),
    TextNotUnique(usize),
    TextNotFound,
    IndexNotReady,
    Glob(globset::Error),
    Regex(String),
    Internal(String),
}
```

错误会自动转换为 Python 异常：
- `Io` → `PyIOError`
- `PathNotFound`/`Pattern`/`TextNotUnique`/`TextNotFound` → `PyValueError`
- `IndexNotReady`/`Internal` → `PyRuntimeError`
