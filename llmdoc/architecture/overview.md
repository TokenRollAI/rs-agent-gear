# Agent-Gear 架构概览

## 设计目标

Agent-Gear 旨在解决 AI Agent 在大规模代码库场景下的文件系统操作瓶颈：

1. **有状态索引**: 启动即建立内存文件树，后续查询走内存
2. **高并发**: 利用 Rust 多线程能力，释放 Python GIL
3. **低延迟**: 批量操作减少 Python/Rust 上下文切换
4. **原子性**: 安全的文件写入保证

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     Python Layer                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  agent_gear/                                         │    │
│  │  ├── __init__.py    (FileSystem wrapper)            │    │
│  │  ├── _rust_core.pyi (Type stubs)                    │    │
│  │  └── fs/            (Submodule)                     │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ PyO3 Bridge
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Rust Layer                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  src/                                                │    │
│  │  ├── lib.rs         (PyO3 module entry)             │    │
│  │  ├── fs/                                            │    │
│  │  │   ├── mod.rs     (FileSystem pyclass)            │    │
│  │  │   ├── io.rs      (Batch I/O)                     │    │
│  │  │   ├── index.rs   (Memory index)                  │    │
│  │  │   ├── searcher.rs(Grep engine)                   │    │
│  │  │   └── atomic.rs  (Atomic write)                  │    │
│  │  └── utils/                                         │    │
│  │      └── error.rs   (Error types)                   │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 关键技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| Python 绑定 | PyO3 0.23 | 成熟稳定，ABI3 支持 |
| 并发索引 | DashMap | 高性能并发 HashMap |
| 数据并行 | Rayon | 简单高效的并行迭代 |
| 目录遍历 | ignore crate | 自动处理 .gitignore |
| 文件监听 | notify crate | 跨平台文件事件 |
| 搜索引擎 | grep-regex | ripgrep 核心库 |

## 数据流

### 初始化流程

```
FileSystem.__init__(root)
    │
    ▼
创建 FileIndex 实例
    │
    ▼
启动后台线程 ──────► 并行扫描目录 (ignore::WalkParallel)
    │                      │
    ▼                      ▼
立即返回给用户        填充 DashMap 索引
                          │
                          ▼
                    标记 is_ready = true
```

### 查询流程

```
fs.list("**/*.py")
    │
    ▼
检查 is_ready? ──(否)──► 返回 IndexNotReady 错误
    │
   (是)
    │
    ▼
编译 Glob 模式
    │
    ▼
遍历内存索引 (DashMap)
    │
    ▼
返回匹配路径列表
```

### 搜索流程

```
fs.grep("pattern", "**/*.py")
    │
    ▼
py.allow_threads() ──► 释放 GIL
    │
    ▼
收集匹配文件列表
    │
    ▼
Rayon 并行搜索 ──► 每个文件独立处理
    │                  │
    │                  ▼
    │              读取文件内容
    │                  │
    │                  ▼
    │              正则匹配
    │                  │
    │                  ▼
    │              收集结果
    │
    ▼
合并结果，截断到 max_results
    │
    ▼
返回 SearchResult 列表
```

## 性能特性

| 操作 | 复杂度 | 说明 |
|------|--------|------|
| `list`/`glob` | O(n) | n = 索引条目数，纯内存操作 |
| `read_batch` | O(k) | k = 文件数，并行 I/O |
| `grep` | O(n*m) | n = 文件数，m = 平均文件大小 |
| `write_file` | O(m) | m = 内容大小，原子写入 |

## 线程模型

```
Main Python Thread
    │
    ├── GIL 保护的 Python 代码
    │
    └── py.allow_threads() ──► Rayon 线程池
                                    │
                                    ├── Worker 1: 文件搜索
                                    ├── Worker 2: 文件搜索
                                    └── Worker N: 文件搜索

Background Index Thread (独立)
    │
    └── 目录扫描和索引构建
```
