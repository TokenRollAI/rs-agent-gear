# PythonFileBackend API 参考

本文档提供 `PythonFileBackend` 类的完整 API 参考，这是外部路径支持的核心实现。

## 1. 核心摘要

**PythonFileBackend** 是一个纯 Python 文件系统操作后端，用于处理初始化根目录之外的路径。它使用 Python 标准库（`pathlib`, `os`, `re` 等）提供与 Rust 实现兼容的 API。

**位置：** `agent_gear/python_backend.py`

**主要职责：**
- 读取外部文件（完整、按行、按字节范围）
- 写入和编辑外部文件（原子写入和快速写入）
- 列出和匹配外部目录中的文件
- 搜索外部文件内容
- 获取文件元数据

---

## 2. API 参考

### 初始化

```python
from agent_gear.python_backend import PythonFileBackend

# 基础初始化
backend = PythonFileBackend()

# 指定最大文件大小（搜索时的限制）
backend = PythonFileBackend(max_file_size_mb=50)
```

**参数：**
- `max_file_size_mb` (int, 默认: 10): 搜索操作的最大文件大小限制，单位为 MB

---

### 文件读取

#### `read_file(path, encoding="utf-8")`

读取整个文件内容。

**参数：**
- `path` (str): 绝对文件路径
- `encoding` (str): 文本编码，默认 `utf-8`

**返回：**
- (str) 文件内容

**异常：**
- `FileNotFoundError`: 文件不存在
- `ValueError`: 路径不是文件
- `UnicodeDecodeError`: 编码错误

**示例：**
```python
backend = PythonFileBackend()
content = backend.read_file("/tmp/file.txt")
```

---

#### `read_lines(path, start_line=0, count=None, encoding="utf-8")`

按行读取文件的指定范围。

**参数：**
- `path` (str): 绝对文件路径
- `start_line` (int): 起始行号（0 索引），默认 0
- `count` (int | None): 要读取的行数。None 表示读取到文件末尾
- `encoding` (str): 文本编码，默认 `utf-8`

**返回：**
- (list[str]) 行列表（不含尾随换行符）

**异常：**
- `FileNotFoundError`: 文件不存在

**示例：**
```python
# 读取前 100 行
lines = backend.read_lines("/tmp/file.txt", start_line=0, count=100)

# 从第 50 行开始读取 20 行
lines = backend.read_lines("/tmp/file.txt", start_line=50, count=20)

# 从第 100 行读取到文件末尾
lines = backend.read_lines("/tmp/file.txt", start_line=100)
```

---

#### `read_file_range(path, offset, limit, encoding="utf-8")`

读取文件的指定字节范围。

**参数：**
- `path` (str): 绝对文件路径
- `offset` (int): 字节偏移量（从 0 开始）
- `limit` (int): 最多读取的字节数
- `encoding` (str): 文本编码，默认 `utf-8`

**返回：**
- (str) 指定范围的内容

**异常：**
- `FileNotFoundError`: 文件不存在
- `UnicodeDecodeError`: 编码错误

**示例：**
```python
# 读取前 1KB
content = backend.read_file_range("/tmp/file.bin", offset=0, limit=1024)

# 从位置 100 开始读取 512 字节
content = backend.read_file_range("/tmp/file.bin", offset=100, limit=512)
```

---

### 文件写入

#### `write_file(path, content, encoding="utf-8")`

原子写入文件（使用临时文件 + rename 确保一致性）。

**参数：**
- `path` (str): 绝对文件路径
- `content` (str): 要写入的内容
- `encoding` (str): 文本编码，默认 `utf-8`

**返回：**
- (bool) 总是返回 True（成功）

**异常：**
- `IOError`: 写入失败
- 失败时会清理临时文件

**行为：**
- 如果父目录不存在，会自动创建
- 使用 `fsync()` 确保数据已写入磁盘
- 原子 `rename()` 操作

**示例：**
```python
backend = PythonFileBackend()
backend.write_file("/tmp/output.txt", "Hello, World!")

# 创建新目录和文件
backend.write_file("/tmp/new_dir/config.json", '{"key": "value"}')
```

---

#### `write_file_fast(path, content, encoding="utf-8")`

快速写入文件，不保证原子性（性能更高，风险更高）。

**参数：**
- `path` (str): 绝对文件路径
- `content` (str): 要写入的内容
- `encoding` (str): 文本编码，默认 `utf-8`

**返回：**
- (bool) 总是返回 True（成功）

**异常：**
- `IOError`: 写入失败

**行为：**
- 如果父目录不存在，会自动创建
- 不使用 `fsync()`，数据可能在缓冲区中
- 普通 `write()` 操作，非原子

**使用场景：** 临时文件、日志、非关键数据

**示例：**
```python
backend = PythonFileBackend()
backend.write_file_fast("/tmp/log.txt", "Debug message\n")
```

---

### 文本编辑

#### `edit_replace(path, old_text, new_text, strict=True, encoding="utf-8")`

替换文件中的文本。

**参数：**
- `path` (str): 绝对文件路径
- `old_text` (str): 要查找的文本
- `new_text` (str): 替换文本
- `strict` (bool):
  - `True`: 要求文本恰好出现一次，否则抛出异常
  - `False`: 替换第一个匹配项
- `encoding` (str): 文本编码，默认 `utf-8`

**返回：**
- (bool) `True` 如果进行了替换，`False` 如果未找到（仅在 `strict=False` 时）

**异常：**
- `FileNotFoundError`: 文件不存在
- `ValueError`: 在 `strict=True` 时，如果文本未找到或不唯一

**行为：**
- 使用 `write_file()` 执行原子写入
- 在 `strict=False` 时仅替换第一个匹配项

**示例：**
```python
backend = PythonFileBackend()

# Strict 模式：必须恰好匹配一次
try:
    backend.edit_replace("/tmp/config.txt", "old_value", "new_value", strict=True)
except ValueError as e:
    print(f"替换失败: {e}")

# 容错模式：替换第一个匹配项
replaced = backend.edit_replace(
    "/tmp/file.txt",
    old_text="pattern",
    new_text="replacement",
    strict=False
)
if replaced:
    print("已替换")
else:
    print("未找到匹配项")
```

---

### 文件列表和模式匹配

#### `list_files(path, pattern="**/*", only_files=True)`

列出目录中匹配 glob 模式的文件。

**参数：**
- `path` (str): 基础目录路径
- `pattern` (str): Glob 模式，默认 `**/*`
  - 支持 `*` 匹配任意字符
  - 支持 `**` 递归匹配
  - 支持 `?` 匹配单个字符
  - 支持 `[abc]` 字符类
- `only_files` (bool):
  - `True`: 仅返回文件
  - `False`: 返回文件和目录

**返回：**
- (list[str]) 绝对路径列表，已排序

**示例：**
```python
backend = PythonFileBackend()

# 列出所有文件
all_files = backend.list_files("/tmp")

# 列出所有 Python 文件
py_files = backend.list_files("/tmp", "**/*.py", only_files=True)

# 列出所有文件和目录
all_items = backend.list_files("/tmp", "**/*", only_files=False)

# 列出特定目录
json_files = backend.list_files("/etc", "**/config*.json")
```

---

#### `glob(path, pattern)`

使用 glob 模式匹配文件。

**参数：**
- `path` (str): 基础目录路径
- `pattern` (str): Glob 模式

**返回：**
- (list[str]) 匹配的绝对路径列表

**备注：** 这是 `list_files()` 的便利包装，总是设置 `only_files=True`

**示例：**
```python
backend = PythonFileBackend()

# 匹配所有 .txt 文件
txt_files = backend.glob("/tmp", "**/*.txt")

# 匹配特定模式
config_files = backend.glob("/etc", "**/config*.{yaml,yml,json}")
```

---

### 内容搜索

#### `grep(pattern, path, glob_pattern="**/*", case_sensitive=False, max_results=1000)`

在文件中搜索匹配的行。

**参数：**
- `pattern` (str): 正则表达式模式
- `path` (str): 基础目录路径
- `glob_pattern` (str): 要搜索的文件 glob 模式，默认 `**/*`
- `case_sensitive` (bool):
  - `True`: 大小写敏感
  - `False`: 大小写不敏感（默认）
- `max_results` (int): 最多返回的结果数，默认 1000

**返回：**
- (list[dict]) 搜索结果列表，每个结果包含：
  - `"file"`: 文件路径
  - `"line_number"`: 行号（从 1 开始）
  - `"content"`: 匹配的行内容
  - `"context_before"`: 前文行（列表，当前未实现）
  - `"context_after"`: 后文行（列表，当前未实现）

**异常：**
- `ValueError`: 正则表达式语法错误

**搜索限制：**
- 跳过大于 `max_file_size_bytes` 的文件
- 跳过无法解码的文件
- 跳过权限拒绝的文件
- 在达到 `max_results` 时停止搜索

**示例：**
```python
backend = PythonFileBackend()

# 基础搜索
results = backend.grep("TODO", "/tmp")

# 大小写敏感搜索
results = backend.grep("ERROR", "/var/log", case_sensitive=True)

# 搜索特定文件类型
results = backend.grep(
    "error|warn",
    "/var/log",
    glob_pattern="**/*.log",
    case_sensitive=False,
    max_results=500
)

# 处理结果
for result in results:
    print(f"{result['file']}:{result['line_number']}: {result['content']}")
```

---

### 文件元数据

#### `get_metadata(path)`

获取文件元数据。

**参数：**
- `path` (str): 绝对文件路径

**返回：**
- (dict) 包含以下键的字典：
  - `"size"` (int): 文件大小（字节）
  - `"mtime"` (float): 修改时间（Unix 时间戳）
  - `"is_dir"` (bool): 是否为目录
  - `"is_binary"` (bool): 是否为二进制文件（通过检查前 512 字节是否包含 null 字符）

**异常：**
- `FileNotFoundError`: 文件不存在

**示例：**
```python
backend = PythonFileBackend()

metadata = backend.get_metadata("/tmp/file.txt")
print(f"Size: {metadata['size']} bytes")
print(f"Modified: {metadata['mtime']}")
print(f"Is directory: {metadata['is_dir']}")
print(f"Is binary: {metadata['is_binary']}")
```

---

## 3. 设计和实现细节

### 二进制检测

通过读取文件前 512 字节并检查 null 字符（`\x00`）来实现。

**相关代码：** `agent_gear/python_backend.py:328-336`

### 原子写入实现

```python
# 1. 创建临时文件
temp_path = file_path.with_suffix(file_path.suffix + ".tmp")

# 2. 写入内容
temp_path.write_text(content)

# 3. fsync 确保数据写入磁盘
os.fsync(fd)

# 4. 原子 rename
temp_path.rename(file_path)
```

### 正则表达式编译

对于 `grep` 操作，使用 `re.compile()` 和可选的 `re.IGNORECASE` 标志。

---

## 4. 集成与使用

### FileSystem 中的集成

`FileSystem` 类（`agent_gear/__init__.py`）自动为外部路径操作选择 `PythonFileBackend`：

```python
# 相对路径或 root 内路径 → Rust 实现
content = fs.read_file("relative/path.txt")

# root 外的绝对路径 → PythonFileBackend
content = fs.read_file("/tmp/external.txt")  # 需要 allow_external=True
```

### 与 Rust 实现的兼容性

`PythonFileBackend` 提供的 API 与 Rust `FileSystem` 的 API 兼容，确保无缝集成：

| 操作 | Rust FileSystem | PythonFileBackend |
|------|-----------------|------------------|
| `read_file()` | ✓ | ✓ |
| `read_lines()` | ✓ | ✓ |
| `read_file_range()` | ✓ | ✓ |
| `write_file()` | ✓ | ✓ |
| `edit_replace()` | ✓ | ✓ |
| `list()` | ✓ | ✓ (作为 list_files) |
| `glob()` | ✓ | ✓ |
| `grep()` | ✓ | ✓ |

---

## 5. 性能特性

- **内存效率：** 逐行读取文件，避免大文件一次全部加载
- **并行支持：** `list_files()` 和 `grep()` 可与 `FileSystem.read_batch()` 配合使用
- **文件大小限制：** `grep()` 自动跳过超过 `max_file_size_bytes` 的文件
- **失败容错：** 无法读取的文件被跳过，不会导致操作中断

---

## 6. 相关代码位置

- **源代码：** `agent_gear/python_backend.py`
- **集成点：** `agent_gear/__init__.py:118-290`
- **测试：** `tests/python/test_external_paths.py`
- **使用指南：** `/llmdoc/guides/external-paths.md`

---

## 7. 快速参考

```python
from agent_gear.python_backend import PythonFileBackend

backend = PythonFileBackend()

# 读取
content = backend.read_file("/tmp/file.txt")
lines = backend.read_lines("/tmp/file.txt", 0, 100)
range_content = backend.read_file_range("/tmp/file.txt", 0, 1024)

# 写入
backend.write_file("/tmp/out.txt", "content")
backend.write_file_fast("/tmp/log.txt", "log message")

# 编辑
backend.edit_replace("/tmp/file.txt", "old", "new", strict=True)

# 列表和搜索
files = backend.list_files("/tmp", "**/*.py")
matches = backend.glob("/tmp", "**/*.txt")
results = backend.grep("pattern", "/tmp", "**/*.log")

# 元数据
metadata = backend.get_metadata("/tmp/file.txt")
```

---

**相关文档：**
- [guides/external-paths.md](../guides/external-paths.md) - 使用指南
- [modules/fs-mod.md](../modules/fs-mod.md) - FileSystem 模块详解
