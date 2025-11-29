# Agent-Gear 项目概述

## 1. 项目愿景与目标

**Agent-Gear** 是一个高性能的文件系统操作和内容搜索库，设计用于 AI 代理和 LLM 应用。其核心目标是提供一个统一的、高效的文件系统接口，用于处理代码库分析、文件批量处理和动态内容搜索。

**主要目标：**
- 为 AI 代理提供快速的文件索引和查询能力
- 支持大规模代码库的实时监控和增量更新
- 在 Python 生态中提供 Rust 级别的性能和安全性
- 简化复杂的并发文件操作（读、写、搜索）

---

## 2. 技术栈概述

Agent-Gear 采用 **混合架构**，将 Rust 的性能与 Python 的易用性结合：

### 核心技术栈

| 层级 | 技术 | 用途 |
|-----|------|------|
| **应用层** | Python 3.12+ | 用户 API 和集成接口 |
| **绑定层** | PyO3 (v0.23) | Rust ↔ Python FFI 绑定 |
| **核心层** | Rust (Edition 2021) | 高性能文件系统操作实现 |
| **并发框架** | Rayon, DashMap, crossbeam | 无锁并发和数据并行 |
| **文件操作** | ignore, notify, memmap2 | 目录遍历、文件监听、内存映射 |
| **搜索引擎** | regex, globset | 正则匹配和 Glob 模式匹配 |
| **构建系统** | maturin | Python 扩展模块编译 |

### 关键依赖

**Rust 层：**
- `pyo3`: 0.23（支持 ABI3，多 Python 版本兼容）
- `dashmap`: 并发索引存储（无锁 HashMap）
- `rayon`: 数据并行化处理
- `notify/notify-debouncer-mini`: 文件系统监听
- `tempfile`: 原子文件写入的临时文件管理
- `memmap2`: 大文件的内存映射读取
- `regex, globset`: 模式匹配

**Python 层：**
- `pytest`: 单元测试框架
- `criterion`: 基准测试（Rust 侧）

---

## 3. 核心功能列表

### 文件系统操作

1. **文件列表和查询**
   - `list(pattern, only_files)`: 内存索引查询（O(1)）
   - `glob(pattern)`: Glob 模式匹配查询
   - **快速路径优化**：`**/*` 模式直接返回缓存列表

2. **文件读取**
   - `read_file(path, encoding)`: 单文件同步读取
   - `read_batch(paths)`: 多文件并行读取（Rayon）
   - **GIL 释放**：允许 Python 线程在读取时继续执行

3. **文件写入和编辑**
   - `write_file(path, content)`: 原子写入（临时文件 + fsync + rename）
   - `edit_replace(path, old, new, strict)`: 文本替换
     - `strict=True`: 文本不存在或非唯一时错误
     - `strict=False`: 替换所有匹配项

4. **内容搜索**
   - `grep(query, glob_pattern, case_sensitive, max_results)`: 正则搜索
   - 搜索结果包含行号、上下文（前后行）
   - **性能优化**：预索引过滤 + 并行文件搜索 + mmap 大文件

### 索引系统

1. **后台索引构建**
   - 启动独立线程构建内存索引
   - 递归扫描目录并缓存元数据（文件大小、修改时间）
   - 支持 `.gitignore` 过滤
   - 原子标志 `is_ready()` 检查索引完成状态

2. **增量更新**
   - 支持 `refresh()` 强制重建索引
   - 实时监听文件变动（可选）

### 文件监听系统

1. **自动监听**（可配置启用/禁用）
   - 监听线程独立运行（50ms 轮询间隔）
   - 支持四种事件：Created, Modified, Deleted, Renamed

2. **事件防抖合并**
   - 100ms 时间窗口内合并重复事件
   - 智能合并规则（如 Create + Delete = 无事件）

3. **增量索引更新**
   - 根据文件变动自动更新内存索引

---

## 4. 架构概览：三层线程模型

Agent-Gear 采用**三层独立线程模型**实现并发：

```
Main Python Thread (GIL 保护)
    ├─ PyO3 方法调用
    │   └─ py.allow_threads() 释放 GIL
    │       ├─ Rayon 工作线程（数据并行）
    │       └─ I/O 操作
    │
    ├─ FileIndex 访问（无锁读）
    │   └─ Arc<FileIndex>
    │       ├─ DashMap（无锁并发 HashMap）
    │       └─ RwLock（多读单写）
    │
    ├─ FileWatcher 线程（独立）
    │   └─ 50ms 轮询
    │       └─ process_events() + 索引增量更新
    │
    └─ 索引构建线程（独立）
        └─ 一次性执行 (compare_exchange 互斥)
```

### 核心组件

1. **FileSystem（主类）**
   - 协调索引、搜索、监听的生命周期
   - 提供 Python 用户接口
   - 管理后台线程的创建和销毁

2. **FileIndex（内存索引）**
   - 三层数据结构：
     - `entries`: 路径 → 元数据映射（DashMap）
     - `dir_children`: 目录 → 子项列表（DashMap）
     - `all_files`: 全量文件列表（RwLock<Vec>）
   - 并发安全：DashMap 无锁 + RwLock 多读单写

3. **Searcher（搜索引擎）**
   - 无状态搜索实现
   - 支持两种模式：
     - 直接扫描（索引未就绪时）
     - 预索引过滤（索引就绪时）
   - 大文件使用 mmap 优化

4. **FileWatcher + Debouncer（文件监听）**
   - notify 库包装器（跨平台支持）
   - Debouncer 合并100ms内重复事件
   - 与 FileIndex 集成，实时更新缓存

---

## 5. 性能特点

### 性能优化策略

| 优化类型 | 实现方式 | 效果 |
|---------|--------|------|
| **并发数据结构** | DashMap 无锁 HashMap | 多读者无阻塞 |
| **GIL 释放** | `py.allow_threads()` | I/O 操作不阻塞 Python |
| **数据并行化** | Rayon `par_iter()` | 充分利用多核 CPU |
| **内存索引** | 预索引文件元数据 | list/glob O(n) → O(1) |
| **快速路径** | `**/*` 直接返回缓存 | 单文件列表零成本 |
| **选择性 mmap** | 大文件 (>32KB) 使用 mmap | 减少内存复制 |
| **原子写入** | temp + fsync + rename | 防止文件损坏 |
| **事件防抖** | 100ms 合并窗口 | 减少索引更新次数 |

### 性能基准

**对标对象：** Python 标准库 (`glob`, `pathlib`, `os.walk`) + 外部工具 (`ripgrep`, `grep`)

**典型加速比（1000文件场景）：**
- 列表查询：2.8x - 5.2x 加速
- Glob 匹配：3.1x - 6.8x 加速
- 批量读取：4.2x - 8.5x 加速
- 内容搜索：5.3x - 11.3x 加速

**索引摊销效果：**
- 索引构建成本：约 50-200ms（1000文件）
- 单次查询节省：50-100ms（相比标准库）
- **收支平衡**：约 1-2 次查询即可回本

---

## 6. 项目状态与路线图

### 当前版本：v0.1.0

**已实现功能：**
- ✅ 文件列表、Glob 查询
- ✅ 单文件和批量读取（GIL 优化）
- ✅ 原子文件写入和文本替换
- ✅ 内容搜索（正则 + Glob）
- ✅ 文件监听和增量更新
- ✅ 后台索引构建
- ✅ Python 3.12+ 支持（ABI3）
- ✅ 完整的类型注解和 mypy strict 支持

**测试覆盖：**
- Rust 层：23 个单元测试（原子性、事件合并、搜索逻辑）
- Python 层：26 个集成测试（API 契约验证）
- 基准测试：Criterion + 综合对标测试 + 摊销分析

### 计划中的特性（Phase 2-3）

**Phase 2 - 功能扩展：**
- [ ] 异步 API (`async/await` 支持)
- [ ] 增量搜索缓存
- [ ] 自定义忽略规则（超越 .gitignore）
- [ ] 文件权限管理

**Phase 3 - 性能和生态：**
- [ ] Python 3.11 向后兼容性
- [ ] 批量删除和重命名 API
- [ ] 基于内容的文件去重
- [ ] LSP 集成示例

---

## 7. 关键设计决策

### 为什么选择混合架构（Rust + Python）？

1. **性能与易用性平衡**
   - Rust 提供无锁并发和零开销抽象
   - Python 提供灵活的用户接口和生态集成

2. **GIL 优化**
   - I/O 密集操作释放 GIL，允许 Python 并发
   - Rayon 线程池在真正的多核上运行

3. **类型安全**
   - Rust 类型系统防止运行时错误
   - Python 类型注解 + `.pyi` 文件提供 IDE 支持

### 为什么选择 DashMap 而非 Mutex<HashMap>？

- **性能**：细粒度锁允许多个读者并发访问不同键
- **可扩展性**：避免全局锁的争用（对大规模索引重要）

### 为什么使用防抖而非精确事件？

- **权衡**：减少索引更新次数（避免抖动）
- **代价**：接受 100ms 最大延迟（可接受的权衡）

---

## 8. 文件结构概览

```
agent-gear/
├── src/                          # Rust 核心实现
│   ├── lib.rs                    # PyO3 模块注册
│   └── fs/
│       ├── mod.rs                # FileSystem pyclass (~362 行)
│       ├── io.rs                 # 读/写/替换操作 (~252 行)
│       ├── index.rs              # 内存索引系统 (~540 行)
│       ├── searcher.rs           # 搜索引擎 (~453 行)
│       ├── watcher.rs            # 文件监听 (~368 行)
│       ├── atomic.rs             # 原子写入 (~162 行)
│       └── error.rs              # 错误定义
│
├── agent_gear/                   # Python 包
│   ├── __init__.py               # 主入口和 FileSystem 包装器
│   ├── _rust_core.pyi            # 类型 stub（自动生成）
│   └── fs/__init__.py            # 便捷重导出
│
├── tests/
│   └── python/
│       └── test_filesystem.py    # 26 个集成测试
│
├── benches/
│   └── fs_bench.rs               # Criterion 基准测试
│
├── benchmarks/
│   ├── benchmark.py              # 综合对标基准
│   └── benchmark_repeated.py     # 重复查询摊销分析
│
├── pyproject.toml                # Python 项目配置 + maturin
├── Cargo.toml                    # Rust 项目配置
└── README.md                     # 项目文档
```

---

## 9. 核心交互流程

### 初始化流程

```
Python: FileSystem(root, auto_watch=True)
    └─> Rust::FileSystem::new()
        ├─ 验证路径存在性
        ├─ 创建 Arc<FileIndex>
        ├─ 启动索引构建线程
        │   └─ 并行扫描目录 (ignore crate)
        │   └─ 缓存文件元数据到 DashMap
        │   └─ 标记 is_ready = true
        │
        └─ [可选] 启动监听线程
            └─ notify::RecommendedWatcher 初始化
            └─ 50ms 轮询循环
```

### 查询流程

```
Python: fs.grep(query, "**/*.py")
    └─> Rust::FileSystem::grep()
        │
        ├─ IF index.is_ready()
        │   ├─ index.glob_paths("**/*.py")  # 快速预过滤
        │   └─ Searcher::grep_with_files() # 预收集文件列表
        │
        └─ ELSE
            ├─ Searcher::collect_files()   # Glob 扫描
            └─ files.par_iter().flat_map(search_file)
                ├─ 正则编译
                ├─ 并行搜索（Rayon）
                ├─ 大文件 mmap 优化
                └─ 计数超限则返回
```

### 写入流程

```
Python: fs.write_file(path, content)
    └─> Rust::atomic_write()
        ├─ tempfile::NamedTempFile::new_in(dir)
        ├─ write_all(content)
        ├─ sync_all()  # fsync 到磁盘
        ├─ persist()   # 原子 rename
        └─ [可选] 监听线程检测变动
            └─ 增量更新索引
```

---

## 10. 开发清单

### 快速开始

1. **构建**
   ```bash
   maturin develop  # 开发模式编译
   ```

2. **测试**
   ```bash
   pytest tests/python/
   cargo test  # Rust 单元测试
   ```

3. **基准**
   ```bash
   cargo bench
   python benchmarks/benchmark.py --files 1000
   ```

### 开发约定

- **代码风格**：Rust (rustfmt) + Python (black/ruff)
- **类型检查**：Python (mypy strict mode)
- **文档**：docstring + markdown 文档

---

## 11. 依赖关系图

```
FileSystem (Python 包装)
    │
    └─> _RustFileSystem (PyO3 绑定)
        │
        ├─ Arc<FileIndex>  ◄────────┐
        │   ├─ DashMap<entries>      │ 共享
        │   ├─ RwLock<all_files>     │
        │   └─ is_ready flag         │
        │                            │
        ├─ Searcher                  │
        │   └─ grep_internal()       │
        │       ├─ collect_files()   │
        │       └─ search_file()     │ 并行查询
        │                            │
        ├─ Arc<FileWatcher>          │
        │   └─ Debouncer            │
        │       └─ event合并规则     │
        │                            │
        └─ 后台线程（索引&监听）
            └─ Arc<AtomicBool> (stop_flag)
```

---

## 总结

Agent-Gear 是一个精心设计的混合系统，通过以下方式实现高性能：

1. **无锁并发**：DashMap + Rayon + 原子操作
2. **GIL 优化**：I/O 操作释放 GIL，允许 Python 并发
3. **智能缓存**：预索引 + 快速路径 + mmap 优化
4. **事件合并**：防抖系统减少冗余更新
5. **安全保证**：原子写入 + 类型系统 + 完整测试

它特别适合 AI 代理需要频繁查询和修改代码库的场景，提供了 **性能、安全和易用性** 的最优组合。

最后更新: 2025-11-29
