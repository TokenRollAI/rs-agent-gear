# Agent-Gear 编码规范

## Rust 规范

### 错误处理：thiserror + PyErr 转换

- 使用 `thiserror::Error` 派生宏定义错误类型
- 实现 `From<AgentGearError> for PyErr` 自动异常转换
- 错误变体需要 `#[error("message")]` 属性

**错误映射：**
- `Io(std::io::Error)` → PyIOError
- `PathNotFound`, `Pattern`, `TextNotUnique`, `TextNotFound`, `Glob`, `Regex` → PyValueError
- `IndexNotReady`, `Internal` → PyRuntimeError

参考：`src/utils/error.rs` (AgentGearError enum 47-67 行)

### 并发原语使用

| 原语 | 场景 | 特性 |
|------|------|------|
| DashMap | 文件元数据、目录索引 | 无锁并发读，细粒度锁 |
| RwLock<T> | 全量文件列表 | 多读单写 |
| AtomicBool | 索引就绪、构建状态 | 原子 CAS，无锁 |
| AtomicUsize | 搜索结果计数 | fetch_add，Ordering::Relaxed |
| Arc<T> | 跨线程共享所有权 | FileIndex、FileWatcher、stop_flag |

参考：`src/fs/index.rs` (FileIndex struct)、`src/fs/mod.rs` (FileSystem 初始化)

### GIL 释放策略：py.allow_threads()

**所有阻塞 I/O 必须释放 GIL：**
- 文件读写：`std::fs::read_to_string()`, `atomic_write()`
- 批量操作：`paths.par_iter()`
- 目录遍历：`ignore::WalkBuilder`

模式：`py.allow_threads(|| { /* 并行代码 */ })`

参考：`src/fs/io.rs` (read_batch 44-64 行)

### PyO3 绑定最佳实践

**核心属性：**
- `#[pymodule]` - 模块入口，注册所有公开类
- `#[pyclass]` - Python 可见的 Rust 类型
- `#[pymethods]` - 公开方法块
- `#[new]` - 构造函数
- `#[pyo3(signature = (...))]` - 默认参数和关键字参数
- `#[pyo3(get)]` - 只读属性

**文档（三斜杠注释）：**
- 第一行：单行概括
- 参数、返回值、异常用 `# Arguments` 等标题
- 支持 Markdown 格式

参考：`src/lib.rs`, `src/fs/mod.rs` (FileSystem class 定义)

---

## Python 规范

### 类型注解：Python 3.12+

**强制要求：**
- 所有函数参数和返回值必须标注
- 使用现代语法：`list[T]`, `dict[K, V]`（无需 typing 导入）
- 不允许隐式 Any（mypy strict 模式）

**pyproject.toml 配置：**
```toml
[tool.mypy]
python_version = "3.12"
strict = true
```

参考：`agent_gear/__init__.py` (FileSystem 类，56-147 行)

### ruff 规则集

**启用的检查：**
```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "C4", "PIE", "RET", "SIM"]
```

- E/W - pycodestyle 错误和警告
- F - Pyflakes（未定义、未使用）
- I - isort（导入排序）
- UP - pyupgrade（现代语法）
- B - flake8-bugbear（常见 bug）
- C4 - 优化推导式
- PIE/RET/SIM - 代码简化

行长度限制：100 字符

---

## 通用规范

### 命名约定

| 类型 | 规则 | 示例 |
|------|------|------|
| Rust 结构体/枚举 | PascalCase | `FileSystem`, `AgentGearError` |
| Rust 函数/方法 | snake_case | `read_batch`, `atomic_write` |
| Rust 常量 | SCREAMING_SNAKE_CASE | 无常量定义 |
| Python 类 | PascalCase | `FileSystem`, `FileMetadata` |
| Python 函数/方法 | snake_case | `read_batch`, `wait_ready` |
| Python 私有成员 | 前缀 `_` | `self._inner` |
| 模块/文件名 | snake_case（Rust）| `fs/io.rs`, `fs/index.rs` |

### 文档字符串规范

**Rust（三斜杠）：**
```rust
/// Brief description.
///
/// Detailed explanation.
///
/// # Arguments
/// * `param` - Description
///
/// # Returns
/// Description of return value
```

**Python（PEP 257）：**
```python
def function(param: Type) -> ReturnType:
    """Brief description.

    Detailed explanation.

    Args:
        param: Description

    Returns:
        Description of return value
    """
```

**类文档遵循相同规则，示例包含在 Args 或独立 Example 块**

参考：`agent_gear/__init__.py` (FileSystem 类 docstring)、`src/fs/mod.rs` (FileSystem 文档)

---

## 项目配置参考

| 配置项 | 值 |
|--------|-----|
| Python 最低版本 | 3.12 |
| Rust Edition | 2021 |
| Rust MSRV | 1.75 |
| 构建工具 | maturin（PyO3 绑定） |
| 测试框架 | pytest |
| 代码检查 | mypy + ruff |

参考：`pyproject.toml`, `Cargo.toml`

---

## 快速参考

**创建新模块时：**
1. Rust: 定义错误变体，使用 `thiserror` + `#[error(...)]`
2. Rust: 所有 I/O 操作包裹 `py.allow_threads()`
3. Rust: PyO3 类需要 `#[pyclass]` + `#[pymethods]`
4. Python: 完整的类型注解（3.12+ 语法）
5. 两语言: 文档字符串必填，包含参数和返回值说明

**并发设计决策：**
- 多读无竞争：用 DashMap 或 RwLock
- 计数器/标志：用 Atomic*
- 跨线程共享：用 Arc
- GIL 释放：包裹 `py.allow_threads()`
