# 安全文件操作指南

安全、可靠地对文件进行读写和修改的最佳实践。本指南覆盖基础操作、高级模式和常见陷阱。

## 1. 基础写入 (write_file)

### 场景：创建或覆盖单个文件

**步骤：**

1. 获取 FileSystem 实例
   ```python
   from agent_gear import FileSystem
   fs = FileSystem("/path/to/project")
   ```

2. 调用 `write_file(path, content)`
   ```python
   fs.write_file("output.txt", "Hello, World!")
   ```

3. 验证成功
   - 若未抛异常，文件已原子写入
   - 目录不存在时自动创建

**关键点：**
- 不存在的文件会被创建
- 现有文件会被完全覆盖
- 操作是原子的：要么全写，要么不写

**错误处理：**
```python
try:
    fs.write_file("/root/protected.txt", "content")
except PermissionError:
    print("权限不足")
except IOError as e:
    print(f"磁盘 I/O 错误: {e}")
```

**代码参考：** `src/fs/io.rs:74-76` (write_file) → `src/fs/atomic.rs:26-54` (atomic_write)

---

## 2. 文本替换 (edit_replace)

### 场景：在现有文件中替换特定文本

#### 2.1 安全的唯一替换（Strict 模式）

**步骤：**

1. 准备文件内容
   ```python
   fs.write_file("config.txt", "VERSION=1.0\nBUILD=debug")
   ```

2. 执行严格替换
   ```python
   try:
       success = fs.edit_replace(
           "config.txt",
           old_text="VERSION=1.0",
           new_text="VERSION=2.0",
           strict=True
       )
   except ValueError as e:
       print(f"替换失败: {e}")
   ```

3. 返回值含义
   - `True`: 替换成功
   - 异常 `TextNotFound`: 文本不存在
   - 异常 `TextNotUnique(count)`: 文本出现多次，拒绝替换

**适用场景：**
- 配置文件中的单一字段
- 代码中的特定变量赋值
- 需要精确控制的修改

**代码参考：** `src/fs/io.rs:107-119` (strict 模式检查)

#### 2.2 容错式替换（非 Strict 模式）

**步骤：**

1. 执行容错替换
   ```python
   success = fs.edit_replace(
       "config.txt",
       old_text="DEBUG_MODE",
       new_text="RELEASE_MODE",
       strict=False
   )

   if not success:
       print("文本未找到，文件未修改")
   ```

2. 行为说明
   - 文本不存在：返回 `False`，文件不变
   - 文本唯一出现：返回 `True`，替换成功
   - 文本多处出现：返回 `True`，**替换所有出现**

**适用场景：**
- 不确定文本是否存在
- 可以接受多处替换
- 日志文件、标记替换

**注意陷阱：** 若文本在多处出现且只想替换一个，容错模式会全部替换！

**代码参考：** `src/fs/io.rs:122` (全局替换) 和 `src/fs/io.rs:98-129` (edit_replace 完整逻辑)

---

## 3. 事务性修改模式

### 场景：多步骤文件修改，需要保证一致性

**模式 A: 原子读-修改-写**

```python
def update_config_atomic():
    """原子式更新配置文件的多个字段"""

    # 步骤 1: 读取完整文件
    content = fs.read_file("config.yaml")

    # 步骤 2: 在内存中修改
    modified = content.replace("env: dev", "env: prod")
    modified = modified.replace("debug: true", "debug: false")

    # 步骤 3: 原子写入（失败时原文件不变）
    fs.write_file("config.yaml", modified)
```

**优势：**
- 多个修改作为单一原子操作
- 任意复杂的转换逻辑
- 失败时原文件完全不变

**代码参考：** `src/fs/io.rs:98-130` (edit_replace 整体流程)

**模式 B: 两阶段写入（备份 + 写）**

```python
def safe_update_with_backup():
    """修改前创建备份"""

    # 步骤 1: 读原文件
    original_content = fs.read_file("important.txt")

    # 步骤 2: 创建备份（可选但推荐）
    fs.write_file("important.txt.bak", original_content)

    # 步骤 3: 修改
    modified = original_content + "\n# New section"

    # 步骤 4: 原子写入
    fs.write_file("important.txt", modified)
```

**用途：**
- 关键文件修改
- 需要回滚能力
- 审计日志

---

## 4. 批量读取与写入

### 场景：高效处理多文件

**读取多文件（并行）：**

```python
# 列出所有 Python 文件
py_files = fs.list("**/*.py")

# 批量并行读取（内部使用 Rayon）
contents = fs.read_batch(py_files[:100])

# 处理
for path, content in contents.items():
    if "TODO" in content:
        print(f"Found TODO in {path}")
```

**关键点：**
- `read_batch` 使用 Rayon 并行读取，自动释放 GIL
- 错误的文件被跳过，不影响其他文件
- 返回 `Dict[str, str]`（路径 → 内容）

**代码参考：** `src/fs/io.rs:44-63` (read_batch 实现)

**写入多文件（顺序）：**

```python
# 当前无 write_batch，使用循环
files_to_write = {
    "file1.txt": "content1",
    "file2.txt": "content2",
}

for path, content in files_to_write.items():
    try:
        fs.write_file(path, content)
    except IOError as e:
        print(f"Failed to write {path}: {e}")
        # 继续处理其他文件或回滚
```

---

## 5. 最佳实践

### 5.1 操作前检查

```python
# 检查文件是否存在
import os

if os.path.exists("config.txt"):
    content = fs.read_file("config.txt")
else:
    print("文件不存在，使用默认值")
    content = DEFAULT_CONFIG
    fs.write_file("config.txt", content)
```

### 5.2 错误分类处理

```python
try:
    fs.edit_replace("app.py", "VERSION", "2.0", strict=True)
except ValueError as e:
    if "TextNotFound" in str(e):
        print("版本字符串不存在")
    elif "TextNotUnique" in str(e):
        print("版本字符串出现多次，需要手动处理")
except IOError as e:
    print(f"磁盘错误: {e}")
```

### 5.3 GIL 释放的好处

```python
import threading

# 在后台线程中读写（不阻塞 GIL）
def background_io():
    contents = fs.read_batch(large_file_list)
    # 处理数据...

thread = threading.Thread(target=background_io)
thread.start()

# 主线程继续执行
print("继续处理其他任务，不会被 I/O 阻塞")
```

**代码参考：** `src/fs/io.rs:74-76`、`src/fs/io.rs:97` 的 `py.allow_threads()` 调用

### 5.4 上下文管理器使用

```python
# 自动清理资源（如有实现）
with FileSystem("/path") as fs:
    fs.write_file("temp.txt", "data")
    # 离开 with 块时自动调用 close()
```

**代码参考：** `src/fs/mod.rs:41` 支持 `__enter__` 和 `__exit__`

---

## 6. 常见陷阱

### 陷阱 1: 忘记 strict=False 导致意外错误

**错误：**
```python
# 若配置文件中有多个 "timeout" 字段
fs.edit_replace("config.txt", "timeout", "30", strict=True)
# 抛出异常！
```

**修复：**
```python
# 确认文本唯一性，或使用 strict=False
if "timeout" 在文件中出现一次:
    fs.edit_replace(..., strict=True)
else:
    fs.edit_replace(..., strict=False)  # 替换所有
```

**代码参考：** `src/fs/io.rs:117-119` (strict 模式唯一性检查)

### 陷阱 2: 编码假设（UTF-8 only）

**错误：**
```python
# 若文件是 UTF-16 或 Latin-1，可能崩溃或返回垃圾数据
content = fs.read_file("legacy_file.txt", encoding="latin-1")
```

**注意：** 当前 `read_file` 忽略 encoding 参数，始终使用 UTF-8。

**修复方案：**
```python
# 使用 Python 标准库处理非 UTF-8
with open("legacy_file.txt", "r", encoding="latin-1") as f:
    content = f.read()

# 转换后再用 write_file（若需要 Agent-Gear 的原子性）
fs.write_file("converted.txt", content)
```

### 陷阱 3: 忽视原子性的前提条件

**错误：**
```python
# 跨文件系统的原子性无法保证
fs.write_file("/mnt/external/file.txt", "data")  # 若 /mnt 是网络文件系统

# 若写入中途网络断开，可能产生部分写入
```

**理解：**
- 同一文件系统内：rename 是原子的
- 跨文件系统：可能分解为复制+删除，失败时不安全

**修复：**
```python
# 先写到本地，再复制到外部存储
fs.write_file("/tmp/temp.txt", "data")
import shutil
shutil.copy("/tmp/temp.txt", "/mnt/external/file.txt")
```

### 陷阱 4: 大文件导致内存溢出

**错误：**
```python
# 尝试读取 10GB 文件
content = fs.read_file("huge_file.bin")  # OOM!
```

**解决方案：**
- 当前无流式读取支持
- 使用 Python 标准库的流式方式：
  ```python
  with open("huge_file.bin", "r") as f:
      for chunk in iter(lambda: f.read(8192), ""):
          process(chunk)
  ```

### 陷阱 5: 并发写同一文件

**错误：**
```python
# 多个线程/进程同时修改同一文件
import threading

def update():
    fs.edit_replace("shared.txt", "counter=1", "counter=2")

threads = [threading.Thread(target=update) for _ in range(10)]
for t in threads:
    t.start()
# 竞争条件！最后谁赢不确定
```

**修复：**
```python
# 使用互斥锁
import threading

lock = threading.Lock()

def update():
    with lock:
        fs.edit_replace("shared.txt", "counter=1", "counter=2")
```

**注意：** Agent-Gear 无内置文件锁，应用层需实现同步。

---

## 7. 性能考量

### 7.1 fsync 开销

**现象：** `write_file` 在磁盘写后暂停数毫秒。

**原因：** 原子性需要 fsync() 将数据持久化到磁盘。

**影响：**
- SSD：通常 < 10ms
- HDD：通常 5-50ms
- NFS：可能 > 100ms

**优化建议：**
```python
# 不要在循环中逐个写小文件
for i in range(1000):
    fs.write_file(f"file_{i}.txt", f"data_{i}")  # 很慢，1000 × fsync

# 改为：合并后一次写
all_data = "\n".join([f"data_{i}" for i in range(1000)])
fs.write_file("all.txt", all_data)
```

### 7.2 内存使用

**考量：** read_batch 并行读取会消耗内存。

**优化：**
```python
# 分批读取
batch_size = 100
for i in range(0, len(files), batch_size):
    batch = files[i:i+batch_size]
    contents = fs.read_batch(batch)
    process(contents)
    # 及时释放内存
```

---

## 8. 测试你的代码

### 单元测试示例

```python
import tempfile
import os

def test_atomic_write():
    with tempfile.TemporaryDirectory() as tmpdir:
        fs = FileSystem(tmpdir)

        # 测试创建
        fs.write_file("test.txt", "initial")
        assert os.path.exists(os.path.join(tmpdir, "test.txt"))

        # 测试覆盖
        fs.write_file("test.txt", "modified")
        content = fs.read_file("test.txt")
        assert content == "modified"

def test_edit_replace_strict():
    with tempfile.TemporaryDirectory() as tmpdir:
        fs = FileSystem(tmpdir)

        # Strict 模式：唯一匹配成功
        fs.write_file("config.txt", "name=old")
        result = fs.edit_replace("config.txt", "name=old", "name=new", strict=True)
        assert result == True

        # Strict 模式：不存在则异常
        try:
            fs.edit_replace("config.txt", "notfound", "x", strict=True)
            assert False, "应该抛异常"
        except ValueError:
            pass  # 预期
```

---

## 9. 调试技巧

### 检查文件内容

```python
# 写入后立即读取验证
fs.write_file("output.txt", "test data")
content = fs.read_file("output.txt")
assert content == "test data", f"Mismatch: {content}"
```

### 异常堆栈追踪

```python
import traceback

try:
    fs.edit_replace("file.txt", "old", "new", strict=True)
except Exception as e:
    traceback.print_exc()
    print(f"Exception type: {type(e).__name__}")
    print(f"Exception message: {e}")
```

### 性能分析

```python
import time

start = time.time()
fs.write_file("large.txt", "x" * 1000000)
elapsed = time.time() - start
print(f"Write 1MB took {elapsed*1000:.2f}ms")
```

---

## 10. 相关文档

- `/llmdoc/architecture/atomic-write.md` - 原子写入详细架构
- `/llmdoc/features/fs-watcher.md` - 文件监听（用于检测修改）
- `/llmdoc/modules/fs-mod.md` - FileSystem 模块详解

---

**最后更新：** 2025-11-29 | 指南版本：1.0
