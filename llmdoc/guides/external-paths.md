# 如何使用外部路径支持

本指南说明如何在 Agent-Gear 中操作初始化根目录之外的文件和目录。外部路径支持通过 `allow_external` 参数启用，使用 Python 标准库作为后端实现。

## 1. 启用外部路径支持

### 基础初始化

```python
from agent_gear import FileSystem

# 启用外部路径支持
fs = FileSystem("/project", allow_external=True)
fs.wait_ready()

# 现在可以访问 root 外的文件
content = fs.read_file("/tmp/external_file.txt")
```

### 禁用外部路径（默认）

```python
# 默认情况下，外部路径被阻止
fs = FileSystem("/project")  # allow_external=False

# 这会抛出 ValueError
try:
    fs.read_file("/tmp/external_file.txt")
except ValueError as e:
    print(f"Error: {e}")
```

## 2. 文件读取

### 读取单个外部文件

```python
# 相对于 root 的文件（总是可访问）
content = fs.read_file("config.txt")  # 相对路径

# root 外的绝对路径（需要 allow_external=True）
content = fs.read_file("/tmp/data.txt")
content = fs.read_file("/home/user/documents/notes.md")
```

### 按行读取外部文件

```python
# 读取前 100 行
lines = fs.read_lines("/tmp/large_file.txt", start_line=0, count=100)

# 从第 50 行开始读取 20 行
lines = fs.read_lines("/tmp/large_file.txt", start_line=50, count=20)

# 读取所有剩余行
lines = fs.read_lines("/tmp/file.txt", start_line=100)
```

### 按字节范围读取

```python
# 读取文件的前 1KB
content = fs.read_file_range("/tmp/binary.bin", offset=0, limit=1024)

# 从位置 100 开始读取 512 字节
content = fs.read_file_range("/tmp/file.bin", offset=100, limit=512)
```

### 批量读取混合路径

```python
# 同时读取 root 内和 root 外的文件
paths = [
    "src/main.py",              # 相对路径（root 内）
    "/tmp/external.txt",        # 绝对路径（root 外）
    "tests/test.py",            # 相对路径（root 内）
    "/home/user/config.json",   # 绝对路径（root 外）
]

contents = fs.read_batch(paths)
# 返回: {"src/main.py": "...", "/tmp/external.txt": "...", ...}
```

## 3. 文件列表和搜索

### 列出外部目录中的文件

```python
# 列出 /tmp 中的所有文件
files = fs.list("/tmp/**/*", only_files=True)

# 列出 /tmp 中的所有 Python 文件
py_files = fs.list("/tmp/**/*.py", only_files=True)

# 列出 /home 中的所有 txt 文件
txt_files = fs.list("/home/**/*.txt", only_files=True)
```

### 使用 Glob 模式搜索

```python
# 在外部目录中使用 glob
results = fs.glob("/tmp/**/*.json")
results = fs.glob("/home/user/projects/**/*.md")

# 支持复杂的 Glob 模式
config_files = fs.glob("/etc/**/config*.{yaml,yml,json}")
```

### 在外部目录中搜索内容

```python
# 在外部目录搜索匹配模式的行
results = fs.grep("ERROR", "/var/log/**/*.log")

# 搜索特定文件模式
results = fs.grep("TODO", "/home/user/code/**/*.py", case_sensitive=True)

# 限制搜索结果
results = fs.grep("warn", "/tmp/**/*.txt", max_results=100)

# 获取搜索结果
for result in results:
    print(f"{result.file}:{result.line_number}: {result.content}")
```

## 4. 文件写入和编辑

### 写入外部文件

```python
# 原子写入外部文件
fs.write_file("/tmp/output.txt", "Hello, World!")

# 创建外部目录中的新文件（如果父目录不存在会自动创建）
fs.write_file("/tmp/new_dir/config.json", '{"key": "value"}')
```

### 编辑外部文件

```python
# 替换外部文件中的文本
success = fs.edit_replace(
    "/tmp/config.txt",
    old="old_value",
    new="new_value",
    strict=True  # 仅当恰好匹配一次时替换
)

# 容错模式（不存在时返回 False）
replaced = fs.edit_replace(
    "/tmp/file.txt",
    old="pattern",
    new="replacement",
    strict=False  # 替换第一个匹配项，即使不唯一
)
```

## 5. 性能考虑

### 路径判断和性能分层

Agent-Gear 自动根据路径类型选择实现：

| 路径类型 | 实现 | 性能 | 使用场景 |
|---------|------|------|--------|
| 相对路径 | Rust | 极高 | 常规项目操作 |
| root 内的绝对路径 | Rust | 极高 | 完整路径引用 |
| root 外的路径 | Python | 中等 | 系统文件、外部数据 |

### 优化建议

1. **优先使用相对路径**
   ```python
   # 好：使用相对路径（使用 Rust 实现）
   content = fs.read_file("src/main.py")

   # 避免：不必要的绝对路径
   content = fs.read_file("/absolute/path/to/root/src/main.py")
   ```

2. **批量操作时分离内外路径**
   ```python
   # 不好：混合内外路径
   all_paths = internal_files + external_files
   contents = fs.read_batch(all_paths)  # 内外混合处理

   # 好：分离处理，内部路径仍使用 Rust 加速
   internal_contents = fs.read_batch(internal_files)
   external_contents = {p: fs.read_file(p) for p in external_files}
   ```

3. **避免频繁列出大型外部目录**
   ```python
   # 不好：列出整个 /home 目录
   all_files = fs.list("/home/**/*")

   # 好：指定具体子目录
   my_files = fs.list("/home/user/myproject/**/*.py")
   ```

## 6. 错误处理

### 外部路径被禁用

```python
fs = FileSystem("/project", allow_external=False)

try:
    fs.read_file("/tmp/file.txt")
except ValueError as e:
    print(f"外部路径被禁用: {e}")
    # 输出: 外部路径被禁用: Path '/tmp/file.txt' is outside root directory...
```

### 文件不存在

```python
try:
    fs.read_file("/tmp/nonexistent.txt")
except FileNotFoundError as e:
    print(f"文件不存在: {e}")
```

### 权限错误

```python
try:
    content = fs.read_file("/root/restricted.txt")
except PermissionError as e:
    print(f"权限被拒绝: {e}")
```

### 批量读取中的失败处理

```python
paths = ["src/main.py", "/tmp/maybe_exists.txt"]
contents = fs.read_batch(paths)

# 不存在的外部文件被跳过，不会导致异常
# contents = {"src/main.py": "..."}  # 只有成功读取的文件
```

## 7. 异步支持

### 异步外部路径操作

```python
import asyncio
from agent_gear import AsyncFileSystem

async def process_external_files():
    async with AsyncFileSystem("/project", allow_external=True) as fs:
        await fs.wait_ready()

        # 异步读取外部文件
        content = await fs.read_file("/tmp/data.txt")

        # 异步批量读取
        paths = ["src/main.py", "/tmp/file.txt"]
        contents = await fs.read_batch(paths)

        # 异步搜索
        results = await fs.grep("pattern", "/tmp/**/*.txt")

asyncio.run(process_external_files())
```

## 8. 常见用例

### 用例 1：分析外部日志文件

```python
fs = FileSystem("/project", allow_external=True)
fs.wait_ready()

# 搜索错误日志
errors = fs.grep("ERROR|CRITICAL", "/var/log/**/*.log", case_sensitive=True)
print(f"发现 {len(errors)} 个错误")

for error in errors[:10]:
    print(f"{error.file}:{error.line_number}: {error.content}")
```

### 用例 2：处理配置文件

```python
import json

fs = FileSystem("/app", allow_external=True)

# 从系统配置目录读取配置
config_content = fs.read_file("/etc/myapp/config.json")
config = json.loads(config_content)

# 修改并写入用户配置
user_config_path = os.path.expanduser("~/.myapp/config.json")
fs.write_file(user_config_path, json.dumps(config, indent=2))
```

### 用例 3：处理临时构建产物

```python
import tempfile

fs = FileSystem("/project", allow_external=True)

with tempfile.TemporaryDirectory() as tmpdir:
    # 构建过程将输出写入临时目录
    build_log = f"{tmpdir}/build.log"
    fs.write_file(build_log, "Build started...")

    # 搜索构建错误
    errors = fs.grep("error", f"{tmpdir}/**/*.log")

    # 如果没有错误，复制输出到项目
    if not errors:
        output = fs.read_file(f"{tmpdir}/output.txt")
        fs.write_file("build/output.txt", output)
```

## 9. 故障排查

### 问题：外部路径检查失败

**症状：** 相对路径被错误地识别为外部路径

**原因：** 路径解析问题

**解决方案：**
```python
# 使用 pathlib 规范化路径
from pathlib import Path

fs = FileSystem("/project", allow_external=True)

# 而不是：
path = "../external/file.txt"  # 可能会被解析为外部

# 使用：
abs_path = str(Path("/project").parent / "external" / "file.txt")
content = fs.read_file(abs_path)
```

### 问题：批量读取中的外部文件被跳过

**症状：** `read_batch()` 返回的结果少于输入的路径数

**原因：** 外部文件读取失败（权限、不存在等）

**解决方案：**
```python
# 检查批量读取结果
paths = ["src/main.py", "/tmp/file.txt", "/tmp/maybe_missing.txt"]
contents = fs.read_batch(paths)

missing = set(paths) - set(contents.keys())
if missing:
    print(f"以下文件无法读取: {missing}")
    # 单独处理这些文件
    for path in missing:
        try:
            contents[path] = fs.read_file(path)
        except Exception as e:
            print(f"无法读取 {path}: {e}")
```

## 10. 最佳实践

1. **始终验证 allow_external 设置**
   ```python
   fs = FileSystem("/project", allow_external=True)
   if not fs._allow_external:
       raise RuntimeError("外部路径支持未启用")
   ```

2. **限制外部路径的搜索范围**
   ```python
   # 好：指定具体目录
   results = fs.grep("pattern", "/tmp/myapp/**/*.log")

   # 避免：搜索整个文件系统
   # results = fs.grep("pattern", "/**/*")
   ```

3. **记录外部路径操作**
   ```python
   import logging

   logger = logging.getLogger(__name__)

   def read_with_logging(path: str) -> str:
       logger.info(f"访问外部文件: {path}")
       return fs.read_file(path)
   ```

4. **在生产环境中谨慎启用**
   ```python
   import os

   allow_ext = os.getenv("ALLOW_EXTERNAL_PATHS", "false").lower() == "true"
   fs = FileSystem("/project", allow_external=allow_ext)
   ```

---

**参考文档：**
- [modules/fs-mod.md](../modules/fs-mod.md) - FileSystem API 完整参考
- [architecture/overview.md](../architecture/overview.md) - 架构概览
- [reference/python-backend.md](../reference/python-backend.md) - PythonFileBackend API
