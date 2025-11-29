# 如何使用 FileIndex

本指南演示如何通过 FileSystem 接口利用内存索引进行文件查询和监听。

## 1. 初始化和等待索引就绪

### 步骤 1a: 创建实例并启动背景索引

```python
from agent_gear import FileSystem

# 创建实例，自动启动后台索引线程
fs = FileSystem("/path/to/project", auto_watch=True)
```

- `auto_watch=True` (默认): 启动文件监听线程，自动同步文件变化
- `auto_watch=False`: 仅建立索引，不启动监听

### 步骤 1b: 等待索引完成

```python
# 方案 1: 主动等待
while not fs.is_ready():
    time.sleep(0.1)
print("索引就绪")

# 方案 2: 使用 wait_ready() 简化
fs.wait_ready()
print("索引就绪")
```

**关键点：**
- `is_ready()` 返回 `is_ready` 原子标志的当前值
- 大型项目 (100000+ 文件) 首次索引可能需要秒级时间
- 索引完成前调用查询方法会抛出 `IndexNotReady` 错误

### 步骤 1c: 使用上下文管理器（推荐）

```python
with FileSystem("/path/to/project") as fs:
    fs.wait_ready()

    # 执行查询
    py_files = fs.list("**/*.py")
    print(f"发现 {len(py_files)} 个 Python 文件")

# 自动调用 close() 清理资源
```

**优势：**
- 自动释放线程资源
- 异常时也能清理
- 更加 pythonic

## 2. 文件列表查询

### 步骤 2: 使用 list / glob 查询

```python
fs.wait_ready()

# 查询 1: 列出所有 Python 文件
py_files = fs.list("**/*.py")
for py_file in py_files:
    print(py_file)

# 查询 2: 快速路径 - 列出所有文件
all_files = fs.list("**/*")
print(f"总共 {len(all_files)} 个文件")

# 查询 3: 匹配多个扩展名
src_files = fs.list("**/*.{rs,py,js}", only_files=True)

# 查询 4: 包含目录
all_items = fs.list("src/**", only_files=False)
```

**参数说明：**
- `pattern`: Glob 模式，支持 `**` 递归、`*` 单层通配、`?` 单字符、`[abc]` 字符集
- `only_files=True` (默认): 仅返回文件路径
- `only_files=False`: 返回文件和目录路径

**性能提示：**
- `list("**/*")` 触发快速路径，避免 Glob 编译，最快
- `list("src/**/*.py")` 需要 Glob 编译 + 并行过滤，但仍来自内存索引

## 3. 获取文件元数据

### 步骤 3: 查询单文件元数据

```python
fs.wait_ready()

# 获取单个文件的元数据
metadata = fs.get_metadata("src/main.rs")

# 访问属性
print(f"文件大小: {metadata.size} 字节")
print(f"是否目录: {metadata.is_dir}")
print(f"是否二进制: {metadata.is_binary}")
print(f"修改时间: {metadata.mtime} (Unix 时间戳)")

# 实际应用: 过滤大文件
large_files = [
    f for f in fs.list("**/*")
    if (meta := fs.get_metadata(f)) and meta.size > 1024 * 1024
]
```

**返回值：**
- `FileMetadata` 对象包含: size (u64), mtime (f64), is_dir (bool), is_binary (bool)
- 路径不存在时返回 None

## 4. 性能最佳实践

### 实践 1: 避免重复扫描，缓存查询结果

```python
# 错误做法: 每次循环都重新扫描
for i in range(10):
    py_files = fs.list("**/*.py")  # 每次都查询索引

# 正确做法: 扫描一次，重复使用
py_files = fs.list("**/*.py")
for i in range(10):
    for py_file in py_files:
        process(py_file)
```

### 实践 2: 优先使用 Glob 预过滤，而非全扫描后过滤

```python
# 低效: 列出所有文件再过滤
all_files = fs.list("**/*")
src_py = [f for f in all_files if f.startswith("src/") and f.endswith(".py")]

# 高效: 直接 Glob 查询
src_py = fs.list("src/**/*.py")
```

### 实践 3: 批量读取时，预先用 Glob 收集路径

```python
# 好的做法
py_files = fs.list("**/*.py")
contents = fs.read_batch(py_files)  # 批量并行读取

# 不好的做法（逐个读取）
for py_file in py_files:
    content = fs.read_file(py_file)
```

### 实践 4: 大型项目使用模式过滤

```python
# 项目有 100000+ 文件
# 不推荐: 一次加载所有文件
all_files = fs.list("**/*")  # 可能有数千个元素

# 推荐: 按需查询子目录或特定类型
py_files = fs.list("src/**/*.py")        # 仅 src 下的 Python
test_files = fs.list("tests/**/*.rs")    # 仅测试目录的 Rust
```

## 5. 与 grep 搜索集成

### 步骤 5: 利用索引加速搜索

```python
fs.wait_ready()

# 搜索方案 1: 索引已就绪，自动使用预过滤
results = fs.grep("TODO", "**/*.py")

for result in results:
    print(f"{result.file}:{result.line_number}: {result.content}")

# 搜索方案 2: 搜索时手动指定 max_results
results = fs.grep(
    "error",
    "**/*.rs",
    case_sensitive=True,
    max_results=100  # 限制结果数量
)

# 搜索方案 3: 索引未就绪时，降级到全扫描
# (自动处理，无需显式调用)
if not fs.is_ready():
    # grep 会扫描文件系统替代索引
    results = fs.grep("pattern", "**/*.py")
```

**Grep 与索引的关系：**
- 索引就绪: 先调用 `fs.glob()` 收集文件列表，再搜索（快速）
- 索引未就绪: 直接扫描文件系统匹配 Glob，然后搜索（较慢，但可用）

## 6. 文件监听与增量更新

### 步骤 6a: 启用自动监听

```python
fs = FileSystem("/path/to/project", auto_watch=True)

# 监听线程在后台运行
# 文件创建/修改/删除/重命名事件自动更新索引

fs.wait_ready()

# 编辑文件
with open("/path/to/project/newfile.py", "w") as f:
    f.write("# new file")

# 等待 100ms 防抖窗口（default）
time.sleep(0.15)

# 索引已自动更新
updated_files = fs.list("**/*.py")
assert "newfile.py" in updated_files
```

### 步骤 6b: 手动检查待处理更新

```python
# 获取并处理待处理的文件变化事件
pending_count = fs.pending_changes()
print(f"待处理 {pending_count} 个文件变化")

# 该操作会处理 Debouncer 中的事件
# 返回成功处理的事件数量
```

### 步骤 6c: 禁用监听（仅索引）

```python
fs = FileSystem("/path/to/project", auto_watch=False)

# 仅构建一次索引，不监听变化
# 适用于：
# - 批处理任务（读一次，不需要更新）
# - 开发环境中减少系统开销
```

## 7. 常见使用模式

### 模式 1: 代码搜索工具

```python
def search_code(project_path, pattern, file_pattern="**/*.py"):
    with FileSystem(project_path) as fs:
        fs.wait_ready()

        results = fs.grep(pattern, file_pattern, max_results=1000)

        for result in results:
            print(f"{result.file}:{result.line_number}")
            print(f"  {result.content.strip()}")
            print()

# 使用
search_code("/home/user/myproject", "ERROR", "**/*.py")
```

### 模式 2: 批量文件处理

```python
def process_all_python_files(project_path):
    with FileSystem(project_path) as fs:
        fs.wait_ready()

        # 1. 列出所有 Python 文件
        py_files = fs.list("**/*.py")

        # 2. 批量读取内容
        contents = fs.read_batch(py_files)

        # 3. 处理内容
        for file_path, content in contents.items():
            analyze(file_path, content)

def process_all_python_files(project_path):
    with FileSystem(project_path) as fs:
        fs.wait_ready()

        # 1. 列出所有 Python 文件
        py_files = fs.list("**/*.py")

        # 2. 批量读取内容
        contents = fs.read_batch(py_files)

        # 3. 处理内容
        for file_path, content in contents.items():
            analyze(file_path, content)
```

### 模式 3: 自动化重构工具

```python
def refactor_project(project_path):
    with FileSystem(project_path, auto_watch=False) as fs:
        fs.wait_ready()

        # 搜索所有 TODO 注释
        todos = fs.grep("TODO", "**/*.py")

        # 对每个 TODO 位置进行重构
        for result in todos:
            file_path = result.file

            # 读取文件
            content = fs.read_file(file_path)

            # 修改内容
            new_content = refactor_content(content)

            # 原子写入
            fs.write_file(file_path, new_content)

        print(f"重构了 {len(set(r.file for r in todos))} 个文件")
```

## 8. 错误处理

### 常见错误及处理

```python
from agent_gear import FileSystem
from agent_gear._rust_core import IndexNotReady

try:
    fs = FileSystem("/nonexistent/path")
except ValueError as e:
    print(f"路径错误: {e}")

try:
    fs = FileSystem("/valid/path")

    # 错误 1: 未等待索引就绪
    py_files = fs.list("**/*.py")
except RuntimeError as e:  # IndexNotReady
    print("需要等待索引就绪")
    fs.wait_ready()
    py_files = fs.list("**/*.py")

# 错误 2: 批量读取中的文件不存在
try:
    contents = fs.read_batch(["file1.py", "nonexistent.py"])
    # 返回 {"file1.py": "..."} 跳过不存在的文件
except Exception as e:
    print("某些文件读取失败", e)

# 错误 3: Glob 模式错误
try:
    fs.list("[invalid glob pattern")
except ValueError as e:
    print(f"Glob 错误: {e}")
```

## 9. 验证任务完成

### 验证清单

- [ ] 创建 FileSystem 实例
- [ ] 调用 `wait_ready()` 等待索引完成
- [ ] 执行 `list()` 查询并验证返回结果
- [ ] 调用 `get_metadata()` 查看文件属性
- [ ] 执行 `grep()` 搜索并验证索引加速
- [ ] 在 `with` 语句中使用并验证自动清理
- [ ] 通过 `pending_changes()` 检查增量更新

**示例验证脚本：**

```python
import time
from agent_gear import FileSystem

# 测试初始化
fs = FileSystem(".")
assert not fs.is_ready(), "初始应未就绪"

fs.wait_ready()
assert fs.is_ready(), "等待后应就绪"

# 测试查询
files = fs.list("**/*")
assert len(files) > 0, "应找到文件"

# 测试元数据
meta = fs.get_metadata("README.md") or fs.get_metadata(files[0])
assert meta is not None, "应获得元数据"
assert meta.size >= 0, "大小应非负"

# 测试搜索
results = fs.grep("def", "**/*.py", max_results=10)
print(f"搜索成功: {len(results)} 个结果")

# 测试清理
fs.close()
print("所有测试通过")
```

---

**参考文档：**
- `/llmdoc/architecture/file-index.md` - 索引系统架构
- `/llmdoc/features/fs-watcher.md` - 文件监听系统
