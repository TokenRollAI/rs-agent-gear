# 开发环境搭建

## 前置要求

- Python 3.12+
- Rust 1.75+
- maturin 1.4+

## 快速开始

### 1. 克隆仓库

```bash
git clone <repo-url>
cd agent-gear
```

### 2. 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate     # Windows
```

### 3. 安装开发依赖

```bash
pip install maturin pytest pytest-benchmark mypy ruff
```

### 4. 构建和安装

开发模式（推荐）：
```bash
maturin develop
```

或使用 pip editable install：
```bash
pip install -e .
```

### 5. 运行测试

Python 测试：
```bash
pytest tests/python -v
```

Rust 测试（需要单独配置）：
```bash
# 注意：由于 abi3 模式，Rust 测试需要特殊处理
cargo test --no-default-features
```

## 开发工作流

### 修改 Rust 代码后

每次修改 Rust 代码后需要重新构建：

```bash
maturin develop
```

### 修改 Python 代码后

如果只修改了 Python 代码（`agent_gear/` 目录），无需重新构建。

### 类型检查

```bash
mypy agent_gear
```

### 代码格式化

Python：
```bash
ruff format .
ruff check --fix .
```

Rust：
```bash
cargo fmt
cargo clippy
```

## 项目结构

```
agent-gear/
├── Cargo.toml           # Rust 配置
├── pyproject.toml       # Python 配置
├── build.rs             # Rust 构建脚本
├── src/                 # Rust 源码
│   ├── lib.rs          # PyO3 模块入口
│   ├── fs/             # fs 模块
│   └── utils/          # 工具模块
├── agent_gear/          # Python 包
│   ├── __init__.py     # 主入口
│   ├── py.typed        # 类型标记
│   └── _rust_core.pyi  # 类型 stub
├── tests/               # 测试
│   ├── python/         # Python 测试
│   └── rust/           # Rust 测试
├── benches/             # 性能基准
└── llmdoc/              # 文档
```

## Phase 3 API 使用指南

### 大文件按行读取 (read_lines)

高效读取文件的指定行范围，不需要加载整个文件到内存。大文件（>1MB）自动使用 mmap 优化。

```python
from agent_gear import FileSystem

fs = FileSystem("/path/to/project")

# 读取前100行
lines = fs.read_lines("large_file.txt", start_line=0, count=100)

# 读取第1000-1100行
lines = fs.read_lines("large_file.txt", start_line=1000, count=100)

# 读取第100行到文件末尾
lines = fs.read_lines("large_file.txt", start_line=100)

# 异步用法
import asyncio
async def read_async():
    async with AsyncFileSystem("/path/to/project") as fs:
        lines = await fs.read_lines("large_file.txt", 0, 100)
        print(lines)

asyncio.run(read_async())
```

**适用场景：**
- 读取大日志文件的部分内容
- 查看源代码的特定行范围
- 处理超过内存可用量的大文件

### 字节范围读取 (read_file_range)

读取文件的指定字节范围，适用于二进制文件或需要精确字节级操作的场景。

```python
from agent_gear import FileSystem

fs = FileSystem("/path/to/project")

# 读取前1000字节
content = fs.read_file_range("file.bin", offset=0, limit=1000)

# 读取从第5000字节开始的2000字节
content = fs.read_file_range("file.bin", offset=5000, limit=2000)

# 异步用法
import asyncio
async def read_range_async():
    async with AsyncFileSystem("/path/to/project") as fs:
        content = await fs.read_file_range("file.bin", 0, 1024)
        print(content)

asyncio.run(read_range_async())
```

**适用场景：**
- 读取文件头部进行格式识别
- 部分下载恢复
- 二进制文件分析

### 异步 API (AsyncFileSystem)

使用 asyncio.to_thread() 将同步操作转换为异步，所有 I/O 操作都支持 async/await。

```python
import asyncio
from agent_gear import AsyncFileSystem

async def main():
    # 使用上下文管理器
    async with AsyncFileSystem("/path/to/project") as fs:
        # 等待索引就绪
        await fs.wait_ready()

        # 列出文件
        files = await fs.list("**/*.py")
        print(f"Found {len(files)} Python files")

        # 搜索
        results = await fs.grep("TODO", "**/*.py")

        # 批量读取
        contents = await fs.read_batch(files[:10])

        # 新的 Phase 3 API
        lines = await fs.read_lines("large.txt", 0, 50)
        chunk = await fs.read_file_range("data.bin", 0, 1024)

        # 写入操作
        await fs.write_file("output.txt", "content")

# 运行异步程序
asyncio.run(main())
```

**关键特性：**
- 所有 I/O 操作都支持 async/await
- 支持 async with 上下文管理器
- 自动在线程池中运行阻塞操作，不阻塞事件循环
- 与同步 FileSystem 使用相同的底层 Rust 实现

## 调试技巧

### 查看 Rust 日志

设置环境变量：
```bash
RUST_LOG=debug maturin develop
```

### 查看编译警告

```bash
cargo check 2>&1 | grep warning
```

### 性能分析

使用 criterion 运行基准测试：
```bash
cargo bench
```

使用 pytest-benchmark：
```bash
pytest tests/python --benchmark-only
```
