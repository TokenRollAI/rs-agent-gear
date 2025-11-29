# Searcher 架构

## 1. 身份与目的

- **身份：** 高性能搜索引擎，提供类似 grep 的文件内容查询功能
- **目的：** 在大型项目中快速搜索匹配特定模式的代码和文本，支持正则表达式、大小写控制、结果限制等高级特性

## 2. 核心组件

- `src/fs/searcher.rs` (SearchOptions, SearchResult, Searcher): 搜索引擎实现，包括正则编译、文件收集、并行搜索、mmap 大文件优化

## 3. 执行流程（LLM 检索地图）

### 3.1 搜索入口

搜索分为两条路径：

**路径 A：索引优化模式** (当索引就绪时)
- 1. `FileSystem.grep()` 调用 `src/fs/mod.rs:240-260`
- 2. 检查 `is_ready()` 状态，调用 `index.glob_paths(pattern)` 预收集文件
- 3. 委托给 `Searcher.grep_with_files()` `src/fs/searcher.rs:132-141`
- 4. 使用预收集文件列表跳过 glob 扫描阶段

**路径 B：直接扫描模式** (索引未就绪或未启用)
- 1. `FileSystem.grep()` 直接调用 `Searcher.grep()` `src/fs/searcher.rs:120-129`
- 2. 释放 GIL，进入 `grep_internal()` `src/fs/searcher.rs:143-192`
- 3. 执行完整搜索流程

### 3.2 核心搜索流程（grep_internal）

**第一阶段：正则编译** `src/fs/searcher.rs:151-158`
- 根据 `case_sensitive` 标志选择编译模式
- 大小写不敏感：使用 `RegexBuilder::case_insensitive(true)`
- 错误转换为 `AgentGearError::Regex`

**第二阶段：文件收集** `src/fs/searcher.rs:161-168`
- 优化路径：若有 `pre_collected_files`，直接使用
- 常规路径：调用 `collect_files()` 进行 glob 匹配和过滤

**第三阶段：并行搜索** `src/fs/searcher.rs:175-186`
- 使用 `Rayon::par_iter()` 并行遍历文件
- 原子计数器 `result_count` 跟踪结果数量
- 检查 `Ordering::Relaxed` 是否达到 `max_results` 上限
- 每个工作线程调用 `search_file()` 搜索单文件

**第四阶段：结果截断** `src/fs/searcher.rs:189`
- 由于并行化可能轻微超出 `max_results`，执行最终截断
- 确保返回结果数量不超过上限

### 3.3 文件收集器（collect_files）

`src/fs/searcher.rs:195-232`

流程：
- 1. 初始化 `ignore::WalkBuilder` 并行遍历
- 2. 配置：`hidden(false)`（包含隐藏文件），`git_ignore(true)`（尊重 .gitignore）
- 3. 对每个路径条目执行过滤：
  - 跳过目录（仅保留文件）
  - 检查文件大小，超过 `max_file_size` 跳过
  - Glob 模式匹配（相对路径）
  - 二进制检测，跳过二进制文件

### 3.4 单文件搜索（search_file）

`src/fs/searcher.rs:235-318`

**大小文件判定：** 32KB 分界
- **小文件（≤32KB）：** 使用 `std::fs::read_to_string()`
- **大文件（>32KB）：** 使用 memmap2 内存映射

**mmap 优势：**
- 减少内存复制开销
- 操作系统管理页面缓存
- 适合一次性大文件搜索

**搜索过程：**
- 1. 读取文件内容（分支处理）
- 2. 按行分割：`content.lines().collect::<Vec<&str>>()`
- 3. 逐行遍历，调用 `regex.is_match(line)`
- 4. 匹配时收集前/后上下文行
- 5. 构建 `SearchResult` 对象
- 6. 原子操作 `result_count.fetch_add(1, Ordering::Relaxed)` 增量计数
- 7. 检查是否达到上限，提前退出

**上下文收集：** `src/fs/searcher.rs:291-303`
- `context_before`：包含前 N 行（从 `saturating_sub()` 开始）
- `context_after`：包含后 N 行（到 `min(lines.len())`）
- 仅当 `options.context_lines > 0` 时执行

### 3.5 二进制文件检测

`src/fs/searcher.rs:321-331`

- 读取文件前 512 字节
- 检查是否包含 null 字节 `buffer.contains(&0)`
- 存在 null 字节判定为二进制，跳过搜索

## 4. 关键数据结构

### SearchOptions（搜索配置）

`src/fs/searcher.rs:16-65`

```
case_sensitive: bool          // 大小写敏感（默认 false）
max_results: usize            // 结果数量限制（默认 1000）
max_file_size: u64            // 文件大小限制（默认 10MB）
context_lines: usize          // 上下文行数（默认 0）
```

### SearchResult（搜索结果）

`src/fs/searcher.rs:68-106`

```
file: String                  // 相对路径
line_number: u32              // 1-indexed 行号
content: String               // 匹配行内容
context_before: Vec<String>   // 前置上下文行
context_after: Vec<String>    // 后置上下文行
```

## 5. 设计优化

### 5.1 索引预过滤

**关键优化：** 使用内存索引的文件列表而不是重新扫描

路径：`FileSystem.grep()` → 检查 `index.is_ready()` → 调用 `index.glob_paths(pattern)` → `grep_with_files()`

**效果：** 避免重复的目录遍历和 .gitignore 解析，特别在大项目中收益显著

### 5.2 mmap 大文件优化

**分界点：** 32KB（`32 * 1024` 字节）

**选择理由：**
- 32KB 是典型内存页面大小的倍数
- 小文件的 mmap 开销超过收益
- 大文件 mmap 降低内存复制，特别对于多核搜索

**实现：** `src/fs/searcher.rs:252-272`

### 5.3 并行搜索与原子计数

**并发模式：** Rayon `par_iter()` + `Arc<AtomicUsize>`

**计数机制：**
```
每个工作线程调用 result_count.fetch_add(1, Ordering::Relaxed)
主线程检查 result_count.load(Ordering::Relaxed) >= max_results 提前退出
```

**内存顺序：** `Ordering::Relaxed` - 仅保证原子性，不提供同步屏障（性能优先）

### 5.4 结果截断

**原因：** 并行化中多个线程可能同时检查上限，导致轻微超出

**解决：** `src/fs/searcher.rs:189` 最终 `.take(max_results)` 截断

### 5.5 二进制文件跳过逻辑

**触发时机：**
- 索引构建阶段（在 `index.rs` 中）
- 直接搜索阶段（在 `collect_files()` 中）

**检测方法：** 前 512 字节包含 null 字节

**优势：** 快速、准确，避免解码错误和搜索污染

## 6. 性能特性

### 并行性
- Rayon 工作窃取调度，利用多核
- GIL 释放，允许真正的并行执行
- 独立文件搜索，无共享状态竞争

### 内存效率
- DashMap 预索引避免重复扫描
- mmap 减少大文件内存复制
- 流式行遍历，不加载完整内容到结构化内存

### 时间复杂度
- 预索引模式：O(n log m)，n=文件数，m=每文件行数
- 直接扫描：O(n log n) 由于 glob 匹配
- 单文件搜索：O(m*|pattern|)，正则匹配复杂度

