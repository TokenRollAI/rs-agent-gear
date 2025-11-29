# 搜索模式指南

本指南展示如何使用 grep API 执行各类搜索操作。

## 1. 基础搜索

### 1.1 最简单的搜索

```python
from agent_gear import FileSystem

with FileSystem("/path/to/project") as fs:
    fs.wait_ready()  # 等待索引构建

    # 在所有文件中搜索 "TODO"
    results = fs.grep("TODO")
    for result in results:
        print(f"{result.file}:{result.line_number}: {result.content}")
```

**参数说明：**
- `query`：搜索字符串或正则表达式
- 其他参数使用默认值（所有文件，不区分大小写，最多 1000 结果）

### 1.2 指定文件类型搜索

```python
# 仅搜索 Python 文件
results = fs.grep("def ", "**/*.py")

# 仅搜索 src 目录下的 Rust 文件
results = fs.grep("fn ", "src/**/*.rs")

# 搜索多个扩展名（使用正则）
results = fs.grep("import", "**/*.{py,js,ts}")
```

## 2. 大小写控制

### 2.1 大小写不敏感搜索（默认）

```python
# 搜索 "error" 会匹配 "Error", "ERROR", "error"
results = fs.grep("error")
```

### 2.2 大小写敏感搜索

```python
# 仅匹配精确大小写
results = fs.grep("Error", case_sensitive=True)

# 或使用配置对象
from agent_gear._rust_core import SearchOptions

options = SearchOptions(case_sensitive=True)
results = fs.grep("Error", "**/*", options)
```

## 3. 正则表达式

### 3.1 基本正则

```python
# 匹配函数定义
results = fs.grep(r"^def \w+\(", "**/*.py")

# 匹配数字
results = fs.grep(r"\d{3}-\d{4}", "**/*.txt")

# 匹配 URL
results = fs.grep(r"https?://[^\s]+", "**/*.md")
```

### 3.2 常用正则模式

```python
# TODO/FIXME 注释
results = fs.grep(r"(TODO|FIXME|HACK):", "**/*.py")

# 导入语句
results = fs.grep(r"^from .* import", "**/*.py")

# 函数调用
results = fs.grep(r"\w+\([^)]*\)", "**/*.rs")

# 配置键值对
results = fs.grep(r"^\s*\w+\s*=", "**/*.toml")
```

### 3.3 特殊正则字符

在 Python 字符串中，需要转义反斜杠：

```python
# 匹配路径分隔符
results = fs.grep(r"path[\\\/]to", "**/*.py")

# 匹配制表符
results = fs.grep(r"\t", "**/*.py")

# 匹配行开始/结束
results = fs.grep(r"^#!", "**/*")  # Shebang
results = fs.grep(r";\s*$", "**/*.js")  # 分号结尾
```

## 4. 结果数量限制

### 4.1 限制最大结果数

```python
# 仅返回前 10 个结果
results = fs.grep("warning", max_results=10)

# 返回所有结果（设置很大的数值）
results = fs.grep("warning", max_results=100000)
```

### 4.2 检查是否超限

```python
results = fs.grep("warning", max_results=100)

if len(results) == 100:
    print("结果可能被截断，请调整搜索条件")
else:
    print(f"找到 {len(results)} 个结果")
```

## 5. 文件大小限制

### 5.1 配置最大文件大小

```python
from agent_gear._rust_core import SearchOptions

# 仅搜索小于 1MB 的文件
options = SearchOptions(max_file_size=1024*1024)
results = fs.grep("config", "**/*.yaml", options)

# 仅搜索小于 100KB 的文件
options = SearchOptions(max_file_size=100*1024)
results = fs.grep("secret", "**/*.env", options)
```

### 5.2 跳过大型二进制文件

```python
# Searcher 自动跳过：
# 1. 包含 null 字节的文件（二进制检测）
# 2. 超过 max_file_size 的文件
# 3. .gitignore 中排除的文件

# 不需要手动处理
results = fs.grep("test", "**/*")  # 自动安全
```

## 6. 上下文行

### 6.1 获取匹配周围的代码

```python
from agent_gear._rust_core import SearchOptions

# 显示匹配前后各 2 行
options = SearchOptions(context_lines=2)
results = fs.grep("raise", "**/*.py", options)

for result in results:
    print(f"--- {result.file}:{result.line_number} ---")
    for line in result.context_before:
        print(f"  {line}")
    print(f"> {result.content}")
    for line in result.context_after:
        print(f"  {line}")
```

### 6.2 上下文用于分析代码

```python
# 找 try-except 块
options = SearchOptions(context_lines=5)
results = fs.grep(r"except\s+\w+", "**/*.py", options)

for result in results:
    # context_before 包含 try 和前置代码
    # content 是 except 行
    # context_after 包含异常处理代码
    print(f"异常处理: {result.file}:{result.line_number}")
```

## 7. 综合示例

### 7.1 代码审计：找所有数据库连接

```python
from agent_gear._rust_core import SearchOptions

options = SearchOptions(
    case_sensitive=False,
    max_results=500,
    context_lines=2
)

# 搜索可能的数据库连接字符串
patterns = [
    r"(mysql|postgres|mongodb)://",
    r"connection_string\s*=",
    r"db\s*=\s*['\"]",
]

for pattern in patterns:
    results = fs.grep(pattern, "**/*.py", options)
    if results:
        print(f"\n匹配 {pattern}:")
        for result in results:
            print(f"  {result.file}:{result.line_number}")
```

### 7.2 性能分析：找所有日志调用

```python
# 检查日志量分布
results = fs.grep(r"(log\.|logger\.|print\()", "**/*.py")

files_with_logs = {}
for result in results:
    files_with_logs[result.file] = files_with_logs.get(result.file, 0) + 1

# 找日志最多的文件
for file, count in sorted(files_with_logs.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"{file}: {count} 条日志")
```

### 7.3 依赖分析：找所有 import

```python
# 统计使用的第三方库
results = fs.grep(r"^import|^from", "**/*.py")

imports = {}
for result in results:
    # 提取第一个单词作为库名
    parts = result.content.split()
    if len(parts) > 1:
        lib = parts[1].split(".")[0]
        imports[lib] = imports.get(lib, 0) + 1

for lib, count in sorted(imports.items(), key=lambda x: x[1], reverse=True):
    print(f"{lib}: {count} 次导入")
```

## 8. 性能优化建议

### 8.1 等待索引就绪

```python
fs = FileSystem("/path/to/project")

# 等待索引构建完成
fs.wait_ready()

# 之后的搜索会使用预索引，速度快 10 倍
results = fs.grep("search_query")
```

### 8.2 缩小搜索范围

```python
# 效率低：搜索所有文件
results = fs.grep("TODO")  # O(n) 文件扫描

# 效率高：缩小 glob 模式
results = fs.grep("TODO", "src/**/*.py")  # 仅扫描 src 下的 Python 文件

# 效率最高：再加上文件大小限制
from agent_gear._rust_core import SearchOptions
options = SearchOptions(max_file_size=1024*1024)
results = fs.grep("TODO", "src/**/*.py", options)
```

### 8.3 调整结果限制

```python
# 如果只需要少数结果，设置较小的 max_results
# 搜索引擎达到限制后会提前停止
results = fs.grep("error", max_results=10)

# 而不是搜索所有后再截断
# results = fs.grep("error")[:10]  # 低效
```

### 8.4 正则优化

```python
# 低效：宽松的正则
results = fs.grep(r".*error.*", "**/*.log")

# 高效：精确的正则
results = fs.grep(r"\[ERROR\]", "**/*.log")

# 原因：正则引擎减少回溯
```

## 9. 常见问题

### 9.1 "结果超过 max_results"

```python
# 问题：搜索太宽泛
results = fs.grep("the")  # 可能返回 1000 个结果

# 解决：缩小搜索范围
results = fs.grep("the", "**/*.py", case_sensitive=True)
results = fs.grep(r"\bthe\b", "**/*.py")  # 完整词匹配
```

### 9.2 搜索未找到预期结果

```python
# 检查：大小写敏感
results = fs.grep("Error", case_sensitive=True)  # 可能为空
results = fs.grep("Error", case_sensitive=False)  # 找到 error/Error/ERROR

# 检查：文件类型
results = fs.grep("import", "**/*.py")  # 仅 Python 文件
results = fs.grep("import", "**/*")  # 所有文件
```

### 9.3 搜索性能缓慢

```python
# 原因 1：索引未就绪
if not fs.is_ready():
    fs.wait_ready()  # 等待 1-10 秒（取决于项目大小）

# 原因 2：搜索范围太大
results = fs.grep("pattern", "**/*")  # 搜索所有文件，包括 node_modules

# 解决：排除大目录（在 .gitignore 中配置）
# Searcher 自动尊重 .gitignore
```

## 10. 与索引交互

### 10.1 搜索与文件列表

```python
# 先列出文件，再搜索
files = fs.list("**/*.py")  # 获取文件列表
print(f"共 {len(files)} 个 Python 文件")

# 在这些文件中搜索
results = fs.grep("def ", "**/*.py")
```

### 10.2 刷新索引

```python
# 如果文件系统有外部修改（绕过监听），手动刷新
fs.refresh()

# 或等待监听系统自动更新（100ms 防抖）
import time
time.sleep(0.2)

# 再次搜索会包含新文件
results = fs.grep("pattern")
```

