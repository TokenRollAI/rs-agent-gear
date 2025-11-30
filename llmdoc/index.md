# Agent-Gear 文档索引

欢迎来到 Agent-Gear 项目的完整文档中心。本索引提供所有技术文档的快速导航和分类汇总。

---

## 项目简介

**Agent-Gear** 是一个高性能的文件系统操作和内容搜索库，专为 AI 代理和 LLM 应用设计。通过 Rust 的高性能和 Python 的易用性结合，提供快速的文件索引、批量操作、原子写入和实时文件监听能力。

**核心特性：**
- 内存文件索引 (FileIndex) - O(1) 查询性能
- 高并发搜索引擎 (Searcher) - Rayon 并行处理
- 原子文件写入 - 三步式（临时文件 → fsync → rename）
- 实时文件监听 - 自动增量索引更新
- 跨平台支持 - Linux (inotify) / macOS (FSEvents) / Windows (ReadDirectoryChangesW)
- 外部路径支持 - 访问 root 目录外的文件和目录（Python 后端）

**当前版本：** v0.1.0 (Alpha)

---

## 文档结构说明

本项目文档分为 7 个主要类别，每个类别包含专门的技术文档：

| 类别 | 用途 | 内容类型 |
|------|------|--------|
| **overview/** | 项目概述和愿景 | 高层次的项目定义、目标、技术栈、关键设计决策 |
| **architecture/** | 系统设计文档 | 深入的架构、组件执行流程、LLM 检索地图 |
| **modules/** | 模块详解 | Rust/Python 各模块的实现细节和接口说明 |
| **features/** | 功能文档 | 特定功能（如文件监听）的实现细节 |
| **guides/** | 开发指南 | 操作手册、最佳实践、性能优化、常见模式 |
| **conventions/** | 开发规范 | 代码风格、Git 工作流、命名约定 |

---

## 按类别浏览所有文档

### 📋 Overview（项目概述）

快速理解项目的定义、目标和整体设计。

- **[Agent-Gear 项目概述](./overview/project-overview.md)**
  - 项目愿景与目标、技术栈概述、核心功能列表
  - 三层线程模型、核心组件、性能特点
  - 项目状态、路线图、关键设计决策
  - 文件结构概览、核心交互流程、依赖关系图
  - **长度：** 400+ 行 | **难度：** 入门 | **用途：** 项目概览

---

### 🏗️ Architecture（架构文档）

深入理解系统各个核心组件的设计和交互方式。**这是 LLM 的检索地图，描述了文件之间的执行流程。**

- **[Agent-Gear 架构概览](./architecture/overview.md)**
  - 设计目标、整体架构图、关键技术选型表
  - 数据流（初始化、查询、搜索）、线程模型
  - 性能特性概览
  - **长度：** 150 行 | **难度：** 中级 | **用途：** 架构速查

- **[内存索引系统 (FileIndex)](./architecture/file-index.md)** ⭐ **LLM 检索地图**
  - 核心定义、数据结构（entries, dir_children, all_files, 元数据）
  - 索引构建流程、二进制检测机制
  - 并发模型、快速路径优化、查询接口
  - 增量更新接口（add_path, update_path, remove_path）
  - 并发安全保证、与监听系统的集成
  - **长度：** 260 行 | **难度：** 高级 | **用途：** 索引系统深度理解

- **[文件监听系统 (FileWatcher)](./architecture/file-watcher.md)** ⭐ **LLM 检索地图**
  - 身份与目的、核心组件（ChangeKind, FileChange, Debouncer, FileWatcher）
  - 执行流程（初始化、事件检测、防抖、索引更新、清理）
  - 跨平台实现细节（Linux/macOS/Windows）
  - 并发和线程安全、设计权衡
  - Python API 集成、性能特性
  - **长度：** 230 行 | **难度：** 高级 | **用途：** 监听系统深度理解

- **[Searcher 架构](./architecture/searcher.md)** ⭐ **LLM 检索地图**
  - 身份与目的、核心组件
  - 执行流程（搜索入口、核心流程、文件收集、单文件搜索、二进制检测）
  - 关键数据结构（SearchOptions, SearchResult）
  - 设计优化（索引预过滤、mmap 优化、并行搜索、结果截断）
  - 性能特性（并行性、内存效率、时间复杂度）
  - **长度：** 190 行 | **难度：** 高级 | **用途：** 搜索引擎深度理解

- **[原子写入系统 (Atomic Write)](./architecture/atomic-write.md)** ⭐ **LLM 检索地图**
  - Identity、核心组件、执行流程
  - 基础原子写入（temp 创建、内容写入、fsync、rename）
  - 文本替换流程（读取、唯一性检测、strict 模式、执行替换）
  - 追加写入、权限保留、同文件系统原子性保证
  - 错误处理与恢复、GIL 管理
  - 性能特征、使用约束、设计决策
  - **长度：** 280 行 | **难度：** 高级 | **用途：** 原子写入深度理解

---

### 🔧 Modules（模块详解）

各个主要模块的实现细节和 API 说明。

- **[fs 模块详解](./modules/fs-mod.md)**
  - 模块概述、子模块说明
  - mod.rs (FileSystem 类) - 核心方法列表
  - io.rs (I/O 操作) - read_file, read_batch, write_file, edit_replace
  - index.rs (内存索引) - FileIndex, FileMetadata 数据结构
  - searcher.rs (搜索引擎) - SearchOptions, SearchResult, 关键点
  - atomic.rs (原子写入) - 实现模式
  - 错误处理、Python 异常映射
  - **长度：** 140 行 | **难度：** 中级 | **用途：** 模块接口速查

### 📚 Reference（参考文档）

事实型的 API 参考和概念查询表。

- **[PythonFileBackend API 参考](./reference/python-backend.md)**
  - 核心摘要、初始化参数
  - 文件读取 API (read_file, read_lines, read_file_range)
  - 文件写入 API (write_file, write_file_fast, edit_replace)
  - 列表和模式匹配 API (list_files, glob)
  - 内容搜索 API (grep)
  - 文件元数据 API (get_metadata)
  - 设计实现细节、与 Rust 实现的兼容性
  - **长度：** 450 行 | **难度：** 中级 | **用途：** PythonFileBackend 完整参考

---

### ✨ Features（功能文档）

特定功能的详细实现说明。

- **[文件监听系统](./features/fs-watcher.md)**
  - 概述、架构图
  - 关键组件（FileWatcher, Debouncer, ChangeKind）
  - Python API 使用示例
  - 索引增量更新机制
  - 性能考虑、跨平台注意事项
  - 禁用监听的场景
  - **长度：** 130 行 | **难度：** 初级 | **用途：** 文件监听功能概览

---

### 📚 Guides（开发指南）

开发过程中的操作手册、最佳实践和常见模式。**适合开发者快速上手。**

- **[开发环境搭建](./guides/development.md)**
  - 前置要求、快速开始步骤
  - 创建虚拟环境、安装依赖、构建和安装
  - 运行测试、开发工作流、项目结构
  - 调试技巧、代码格式化、性能分析
  - **长度：** 140 行 | **难度：** 初级 | **用途：** 本地环境设置

- **[搜索模式指南](./guides/search-patterns.md)**
  - 基础搜索、大小写控制、正则表达式
  - 结果数量限制、文件大小限制、上下文行
  - 综合示例（代码审计、性能分析、依赖分析）
  - 性能优化建议、常见问题解答
  - 与索引交互、刷新索引
  - **长度：** 370 行 | **难度：** 中级 | **用途：** grep API 完全指南

- **[安全文件操作指南](./guides/safe-file-operations.md)**
  - 基础写入、文本替换（strict 和容错模式）
  - 事务性修改模式、批量读取与写入
  - 最佳实践、常见陷阱（5 大陷阱+解决方案）
  - 性能考量、测试示例、调试技巧
  - **长度：** 515 行 | **难度：** 中级 | **用途：** 文件操作完全指南

- **[如何使用 FileIndex](./guides/using-file-index.md)**
  - 初始化和等待索引就绪、上下文管理器
  - 文件列表查询、获取文件元数据
  - 性能最佳实践（4 大实践）
  - 与 grep 搜索集成
  - 文件监听与增量更新
  - 常见使用模式（3 大模式）、错误处理
  - 验证任务完成、参考文档
  - **长度：** 400 行 | **难度：** 中级 | **用途：** FileIndex 完全指南

- **[文件监听配置指南](./guides/file-watching.md)**
  - 启用文件监听、索引自动同步机制
  - 事件流处理、禁用监听
  - 跨平台注意事项（Linux/macOS/Windows）
  - 性能调优、错误处理和恢复
  - 上下文管理器用法、常见问题解答
  - 参考链接
  - **长度：** 280 行 | **难度：** 中级 | **用途：** 文件监听配置指南

- **[CI/CD 流程指南](./guides/ci-cd.md)**
  - CI 工作流详解（Rust 测试、Python 测试、类型检查）
  - Release 工作流详解（多平台构建、PyPI 发布）
  - 发布完整流程（版本准备、tag 推送、监控）
  - PyPI Trusted Publisher (OIDC) 配置说明
  - 故障排查和最佳实践
  - **长度：** 480 行 | **难度：** 中级 | **用途：** CI/CD 工作流完全指南

- **[外部路径支持指南](./guides/external-paths.md)**
  - 启用和禁用外部路径支持
  - 读取外部文件（单个、按行、按字节范围）
  - 批量读取混合路径、列出和搜索外部目录
  - 写入和编辑外部文件、性能考虑和优化
  - 错误处理、异步支持、常见用例、故障排查
  - **长度：** 480 行 | **难度：** 中级 | **用途：** 外部路径完全指南

---

### 📖 Conventions（开发规范）

项目开发的标准和约定。**所有贡献者必读。**

- **[编码规范](./conventions/coding-conventions.md)**
  - Rust 规范（错误处理、并发原语、GIL 释放、PyO3 绑定）
  - Python 规范（类型注解、ruff 规则集）
  - 通用规范（命名约定、文档字符串规范）
  - 项目配置参考、快速参考
  - **长度：** 175 行 | **难度：** 初级 | **用途：** 代码风格标准

- **[Git 规范](./conventions/git-conventions.md)**
  - 分支策略（主/开发/功能分支）、分支生命周期
  - 提交消息格式 (Conventional Commits)
  - 版本号管理 (SemVer)、版本发布流程
  - 日常开发流程（开始功能、提交 PR、合并、发布）
  - 提交检查清单、常见命令速查、相关资源
  - **长度：** 290 行 | **难度：** 初级 | **用途：** Git 工作流标准

---

## 快速导航

### 我想...

#### 快速上手（5 分钟）
1. 阅读 [Agent-Gear 项目概述](./overview/project-overview.md) 的前两章了解项目目标
2. 运行 [开发环境搭建](./guides/development.md#快速开始) 中的快速开始步骤
3. 查看 [如何使用 FileIndex](./guides/using-file-index.md#1-初始化和等待索引就绪) 的代码示例

#### 理解架构（30 分钟）
1. 从 [Agent-Gear 架构概览](./architecture/overview.md) 开始
2. 深入阅读组件架构：
   - [内存索引系统 (FileIndex)](./architecture/file-index.md) - 了解索引如何工作
   - [Searcher 架构](./architecture/searcher.md) - 了解搜索如何优化
   - [文件监听系统 (FileWatcher)](./architecture/file-watcher.md) - 了解监听和同步
   - [原子写入系统 (Atomic Write)](./architecture/atomic-write.md) - 了解写入如何安全

#### 进行开发（1 小时）
1. 查看 [编码规范](./conventions/coding-conventions.md) 了解代码标准
2. 按照 [Git 规范](./conventions/git-conventions.md) 进行版本控制
3. 参考具体操作指南：
   - [搜索模式指南](./guides/search-patterns.md) - 处理搜索任务
   - [安全文件操作指南](./guides/safe-file-operations.md) - 处理文件操作
   - [文件监听配置指南](./guides/file-watching.md) - 处理文件变动
4. 理解 CI/CD 流程：
   - [CI/CD 流程指南](./guides/ci-cd.md) - 了解自动化构建和发布

#### 解决问题（实时查询）
- 搜索性能问题：[搜索模式指南 - 常见问题](./guides/search-patterns.md#9-常见问题) 和 [搜索模式指南 - 性能优化建议](./guides/search-patterns.md#8-性能优化建议)
- 文件监听问题：[文件监听配置指南 - 常见问题](./guides/file-watching.md#常见问题)
- 文件操作问题：[安全文件操作指南 - 常见陷阱](./guides/safe-file-operations.md#6-常见陷阱)
- 索引问题：[如何使用 FileIndex - 错误处理](./guides/using-file-index.md#8-错误处理)

---

## 文档地图（按系统组件）

```
Agent-Gear (主系统)
│
├── FileSystem (主类)
│   ├── 核心: FileIndex (内存索引)
│   │   ├── 架构: architecture/file-index.md
│   │   ├── 使用: guides/using-file-index.md
│   │   └── 模块: modules/fs-mod.md (index.rs)
│   │
│   ├── 核心: Searcher (搜索引擎)
│   │   ├── 架构: architecture/searcher.md
│   │   ├── 使用: guides/search-patterns.md
│   │   └── 模块: modules/fs-mod.md (searcher.rs)
│   │
│   ├── 核心: FileWatcher (文件监听)
│   │   ├── 架构: architecture/file-watcher.md
│   │   ├── 使用: guides/file-watching.md
│   │   ├── 功能: features/fs-watcher.md
│   │   └── 模块: modules/fs-mod.md (watcher.rs)
│   │
│   ├── 核心: atomic 模块 (原子写入)
│   │   ├── 架构: architecture/atomic-write.md
│   │   ├── 使用: guides/safe-file-operations.md
│   │   └── 模块: modules/fs-mod.md (atomic.rs)
│   │
│   └── 核心: io.rs (读写操作)
│       ├── 使用: guides/safe-file-operations.md
│       └── 模块: modules/fs-mod.md (io.rs)
│
│   └── 高级: PythonFileBackend (外部路径)
│       ├── 使用: guides/external-paths.md
│       └── 参考: reference/python-backend.md
│
├── 项目概览
│   ├── overview/project-overview.md
│   └── architecture/overview.md
│
└── 开发规范与流程
    ├── conventions/coding-conventions.md
    ├── conventions/git-conventions.md
    ├── guides/development.md
    ├── guides/ci-cd.md (CI/CD 自动化流程)
    └── guides/external-paths.md (外部路径支持)
```

---

## 概念术语表

| 术语 | 定义 | 相关文档 |
|------|------|--------|
| **FileIndex** | 线程安全的内存文件索引，通过 DashMap 提供 O(1) 查询性能 | [file-index.md](./architecture/file-index.md) |
| **Searcher** | 并行搜索引擎，支持正则表达式和 Glob 模式，使用 Rayon 加速 | [searcher.md](./architecture/searcher.md) |
| **FileWatcher** | 跨平台文件监听器，使用 notify crate，通过 Debouncer 防抖事件 | [file-watcher.md](./architecture/file-watcher.md) |
| **Debouncer** | 防抖器，在 100ms 时间窗口内合并和去重文件变动事件 | [file-watcher.md](./architecture/file-watcher.md#32-事件防抖) |
| **原子写入** | temp→fsync→rename 三步模式，保证文件写入的全有或全无语义 | [atomic-write.md](./architecture/atomic-write.md) |
| **GIL 释放** | PyO3 中 `py.allow_threads()` 的使用，允许 I/O 操作不阻塞 Python | [coding-conventions.md](./conventions/coding-conventions.md) |
| **快速路径** | `list("**/*")` 直接返回缓存列表，避免 Glob 编译开销 | [file-index.md](./architecture/file-index.md#5-快速路径优化) |
| **增量更新** | 文件变动时仅更新修改的部分，而非全部重新构建索引 | [file-index.md](./architecture/file-index.md#7-增量更新接口) |
| **DashMap** | 无锁并发 HashMap，支持多个读者无阻塞并发访问 | [file-index.md](./architecture/file-index.md#2-核心数据结构) |
| **Rayon** | Rust 数据并行库，用于并行迭代、过滤、搜索等操作 | [searcher.md](./architecture/searcher.md#34-单文件搜索) |
| **mmap** | 内存映射文件，用于大文件搜索以减少内存复制 | [searcher.md](./architecture/searcher.md#34-单文件搜索) |
| **PythonFileBackend** | 纯 Python 文件系统后端，用于处理 root 目录外的文件 | [python-backend.md](./reference/python-backend.md) |
| **外部路径** | 初始化 root 目录之外的文件和目录（需 `allow_external=True`） | [external-paths.md](./guides/external-paths.md) |

---

## 性能指标概览

| 操作 | 复杂度 | 性能 | 说明 |
|------|--------|------|------|
| `list("**/*")` | O(n) | 快速路径，直接返回缓存 | 1000 文件 < 1ms |
| `list("**/*.py")` | O(n) | Glob 编译 + 并行过滤 | 1000 文件 2-5ms |
| `grep(pattern)` | O(n*m) | Rayon 并行，mmap 大文件 | 1000 文件 50-200ms |
| `read_batch()` | O(k) | Rayon 并行读取，释放 GIL | 100 文件并行 5-20ms |
| `write_file()` | O(m) | fsync 同步到磁盘 | SSD < 10ms，HDD 5-50ms |
| `edit_replace()` | O(m) | 读 + 匹配 + 替换 + 原子写 | 小文件 < 20ms |
| 索引构建 | O(n) | 并行扫描 + DashMap 插入 | 1000 文件 50-200ms |

**加速比示例（对标 Python 标准库）：**
- 列表查询：2.8x - 5.2x 加速
- Glob 匹配：3.1x - 6.8x 加速
- 批量读取：4.2x - 8.5x 加速
- 内容搜索：5.3x - 11.3x 加速

---

## 常见开发任务

### 添加新的 Python API
1. 在 `src/fs/mod.rs` 定义 `#[pymethods]` 方法
2. 按照 [编码规范](./conventions/coding-conventions.md) 编写文档字符串
3. 在 `agent_gear/__init__.py` 的 `FileSystem` 包装器中暴露接口
4. 编写类型 stub（`.pyi` 文件）供类型检查
5. 参考 [如何使用 FileIndex](./guides/using-file-index.md) 编写使用示例

### 优化搜索性能
1. 阅读 [Searcher 架构](./architecture/searcher.md) 了解执行路径
2. 参考 [搜索模式指南 - 性能优化建议](./guides/search-patterns.md#8-性能优化建议)
3. 检查 [搜索模式指南 - 综合示例](./guides/search-patterns.md#7-综合示例)

### 处理文件变动
1. 了解 [文件监听系统 (FileWatcher) 架构](./architecture/file-watcher.md)
2. 查看 [文件监听配置指南](./guides/file-watching.md) 的实际示例
3. 处理 [文件监听配置指南 - 跨平台注意事项](./guides/file-watching.md#步骤-5-跨平台注意事项)

### 安全的文件操作
1. 阅读 [原子写入系统 (Atomic Write)](./architecture/atomic-write.md)
2. 查看 [安全文件操作指南](./guides/safe-file-operations.md)
3. 注意 [安全文件操作指南 - 常见陷阱](./guides/safe-file-operations.md#6-常见陷阱)

### 发布新版本
1. 按照 [Git 规范 - 版本发布流程](./conventions/git-conventions.md#版本发布流程) 准备发布
2. 参考 [CI/CD 流程指南](./guides/ci-cd.md) 了解自动化发布流程
3. 监控 GitHub Actions 构建和 PyPI 发布

---

## 项目状态和路线图

### 当前版本：v0.1.0 (Alpha)

#### Phase 1: 核心功能 ✅ 完成
- ✅ 批量文件读取 (`read_batch`) - Rayon 并行读取，释放 GIL
- ✅ 原子文件写入 (`write_file`) - temp→fsync→rename 模式
- ✅ 文本替换 (`edit_replace`) - 支持 strict 模式检查唯一性
- ✅ 内存文件索引 (`list`, `glob`) - DashMap 并发索引，Rayon 并行查询
- ✅ 高性能搜索 (`grep`) - 使用索引预过滤 + mmap 大文件 + 并行搜索

#### Phase 2: 文件监听 ✅ 完成
- ✅ 文件监听 (File Watching) - 跨平台实时检测 (inotify/FSEvents/ReadDirectoryChanges)
- ✅ 防抖动 (Debouncing) - 100ms 事件合并
- ✅ 索引增量更新 - 自动同步 Create/Modify/Delete/Rename 事件

#### Phase 3: 高级特性 ✅ 完成
- ✅ 大文件按行读取 (`read_lines`) - 支持指定行范围读取，>1MB 文件使用 mmap 优化
- ✅ 字节范围读取 (`read_file_range`) - 支持读取文件指定字节范围
- ✅ Python 异步支持 (AsyncFileSystem) - 使用 asyncio.to_thread() 包装同步方法
- ✅ 上下文行 - grep 支持 context_lines 参数

#### Phase 4: 外部路径支持 ✅ 完成
- ✅ 外部路径支持 (`allow_external` 参数) - 访问 root 目录外的文件
- ✅ PythonFileBackend - 纯 Python 实现的后端，用于超界路径
- ✅ 路径判断逻辑 - 相对/内部路径用 Rust，外部路径用 Python
- ✅ 混合读取 - `read_batch()` 支持混合内/外路径

---

## 测试和验证

### 运行测试
```bash
# Python 测试
pytest tests/python -v

# Rust 测试
cargo test

# 完整测试套件
cargo test && pytest tests/
```

### 代码检查
```bash
# 类型检查
mypy agent_gear

# Python 代码检查
ruff check .

# Rust 代码检查
cargo clippy

# 代码格式化
ruff format .
cargo fmt
```

### 性能基准
```bash
# Rust 基准
cargo bench

# Python 基准
python benchmarks/benchmark.py --files 1000
python benchmarks/benchmark_repeated.py
```

参考 [开发环境搭建](./guides/development.md#调试技巧) 获取更多调试技巧。

---

## 贡献指南

1. **遵循规范**：阅读 [编码规范](./conventions/coding-conventions.md) 和 [Git 规范](./conventions/git-conventions.md)
2. **分支工作流**：按照 [Git 规范 - 日常开发流程](./conventions/git-conventions.md#5-日常开发流程) 创建分支
3. **提交消息**：遵循 [Conventional Commits](./conventions/git-conventions.md#3-提交消息格式) 格式
4. **版本号**：遵循 [语义化版本](./conventions/git-conventions.md#4-版本号管理) 规范
5. **文档更新**：修改代码后同时更新相关 llmdoc 文档
6. **测试**：确保所有测试通过，新功能添加相应测试

---

## 相关资源

### 项目资源
- **项目仓库**：`/home/djj/code/base-tools/`
- **源代码**：`src/` (Rust) 和 `agent_gear/` (Python)
- **测试**：`tests/`
- **基准**：`benches/` 和 `benchmarks/`

### 外部资源
- [Conventional Commits](https://www.conventionalcommits.org/)
- [语义化版本](https://semver.org/lang/zh-CN/)
- [PyO3 官方文档](https://pyo3.rs/)
- [Rust Book](https://doc.rust-lang.org/book/)
- [Python 类型提示](https://docs.python.org/3.12/library/typing.html)

---

## 文档维护

本索引文档最后更新于：**2025-11-30** (外部路径支持文档完成)

文档系统采用以下目录结构：

```
llmdoc/
├── index.md              # 本文件（中心导航）
├── overview/             # 项目概述
│   └── project-overview.md
├── architecture/         # 系统架构（LLM 检索地图）
│   ├── overview.md
│   ├── file-index.md
│   ├── file-watcher.md
│   ├── searcher.md
│   └── atomic-write.md
├── modules/              # 模块详解
│   └── fs-mod.md
├── features/             # 功能实现
│   └── fs-watcher.md
├── guides/               # 开发指南（操作手册）
│   ├── development.md
│   ├── search-patterns.md
│   ├── safe-file-operations.md
│   ├── using-file-index.md
│   ├── file-watching.md
│   ├── ci-cd.md
│   └── external-paths.md # 外部路径支持指南（新增）
├── reference/            # 参考文档
│   └── python-backend.md # PythonFileBackend API（新增）
└── conventions/          # 开发规范
    ├── coding-conventions.md
    └── git-conventions.md
```

### 文档更新流程

1. 修改 llmdoc 文件
2. 验证 Markdown 格式正确
3. 提交到 git 并遵循 Conventional Commits
4. 在 PR 描述中说明文档变更

如需更新文档，请参考 [编码规范 - 文档字符串规范](./conventions/coding-conventions.md#文档字符串规范)。

---

## 快速参考

### 最常用的 API

```python
from agent_gear import FileSystem, AsyncFileSystem
import asyncio

# 初始化
fs = FileSystem("/path/to/project", auto_watch=True)
fs.wait_ready()  # 等待索引完成

# 文件列表
files = fs.list("**/*.py")  # 快速路径
py_files = fs.list("src/**/*.py", only_files=True)

# 文件读取
content = fs.read_file("file.txt")
batch_contents = fs.read_batch(files[:10])

# Phase 3 新增 API - 大文件操作
lines = fs.read_lines("large.txt", start_line=0, count=100)  # 读100行
chunk = fs.read_file_range("data.bin", offset=0, limit=1024)  # 读1024字节

# 搜索
results = fs.grep("TODO", "**/*.py")
results = fs.grep("error", "**/*.log", case_sensitive=True)

# 文件写入
fs.write_file("output.txt", "content")
fs.edit_replace("config.txt", "old", "new", strict=True)

# 监听
if fs.is_watching():
    print("监听活跃")

# 异步 API (Phase 3 新增)
async def async_example():
    async with AsyncFileSystem("/path/to/project") as fs:
        await fs.wait_ready()
        files = await fs.list("**/*.py")
        lines = await fs.read_lines("large.txt", 0, 100)
        results = await fs.grep("TODO", "**/*.py")

asyncio.run(async_example())

# 外部路径支持（Phase 4 新增）
fs = FileSystem("/project", allow_external=True)
external_content = fs.read_file("/tmp/external.txt")
external_files = fs.list("/tmp/**/*.py")
results = fs.grep("TODO", "/var/log/**/*.log")
```

### 关键概念速查

- **索引就绪**：`fs.is_ready()` - 检查后台索引构建是否完成
- **Glob 模式**：`**/*.py` - 递归查找所有 Python 文件
- **Strict 模式**：`edit_replace(..., strict=True)` - 仅替换唯一匹配项
- **GIL 释放**：所有 I/O 操作自动释放 GIL，支持并发
- **防抖窗口**：100ms - 文件监听的事件合并时间
- **按行读取**：`read_lines(path, start_line, count)` - 大文件优化读取，>1MB 使用 mmap
- **字节范围**：`read_file_range(path, offset, limit)` - 读取指定字节范围
- **异步 API**：`AsyncFileSystem` - asyncio.to_thread() 包装，支持 async/await
- **外部路径**：`FileSystem(..., allow_external=True)` - 访问 root 外的文件和目录（Python 后端）

---

**提示：** 本索引是 LLM 的检索入门。为了获得最佳理解，建议按照"快速导航"部分选择合适的学习路径。
