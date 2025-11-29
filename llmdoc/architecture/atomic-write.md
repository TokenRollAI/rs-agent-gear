# 原子写入系统架构

## 1. Identity

- **What it is:** 原子写入（Atomic Write）是确保文件数据完整性的核心机制，使用"临时文件 → fsync → 原子重命名"模式保证写入操作的全有或全无语义。
- **Purpose:** 在任何故障情况下（进程崩溃、断电等），要么文件完全写入，要么保持原状，绝不产生部分写入的损坏文件。

## 2. Core Components

- `src/fs/atomic.rs` (`atomic_write`, `atomic_write_preserve_perms`, `atomic_append`, `create_backup`) - 核心原子操作库，实现 temp→fsync→rename 模式
- `src/fs/io.rs` (`write_file`, `edit_replace`) - 上层 I/O 包装函数，调用 atomic 模块进行安全写入
- `src/fs/mod.rs` (`FileSystem::write_file`, `FileSystem::edit_replace`) - PyO3 暴露的 Python 接口
- `tempfile` 依赖 - 提供自清理临时文件，由 `NamedTempFile::persist()` 实现原子 rename
- `src/utils/error.rs` - 错误类型定义和 Python 异常映射

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 基础原子写入流程（write_file）

1. **参数验证和目录创建**
   - `src/fs/atomic.rs:27-33` 获取父目录，若不存在则创建
   - 使用 `std::fs::create_dir_all()` 确保路径存在

2. **临时文件创建**
   - `src/fs/atomic.rs:37` 在目标目录创建 `NamedTempFile::new_in(dir)`
   - **关键：** 临时文件与目标在同一文件系统，保证后续 rename 的原子性
   - 临时文件遵循操作系统约定命名（如 Linux 的 `.tmp*` 前缀）

3. **内容写入**
   - `src/fs/atomic.rs:40` 使用 `write_all(content)` 一次性写入全部内容
   - 数据存储在用户空间缓冲区（Page Cache）

4. **磁盘同步**
   - `src/fs/atomic.rs:43` 调用 `sync_all()` 强制刷新到磁盘
   - 等效于系统调用 `fsync()`，确保数据物理写入存储介质
   - **性能代价：** fsync 是同步阻塞操作，开销较大

5. **原子重命名**
   - `src/fs/atomic.rs:46` 调用 `persist(path)`
   - `tempfile` crate 使用 `std::fs::rename()` 实现，在同文件系统上保证原子性
   - POSIX 系统：`rename()` 是原子操作（内核层保证）
   - Windows：使用 `ReplaceFileW()` 获得类似原子性
   - 失败则临时文件被自动清理

### 3.2 文本替换流程（edit_replace）

1. **读取原文件** - `src/fs/io.rs:99-105`
   - 调用 `std::fs::read_to_string()` 读取完整内容
   - 捕获文件不存在错误，返回 `PathNotFound`

2. **检测匹配唯一性** - `src/fs/io.rs:108`
   - 使用 `content.matches(old_text).count()` 计数出现次数
   - 三种情况分别处理：
     - `count == 0`：不存在
     - `count == 1`：完美匹配
     - `count > 1`：多处匹配

3. **Strict 模式检查** - `src/fs/io.rs:111-119`
   - `strict=true`：文本不存在返回 `TextNotFound`，多处匹配返回 `TextNotUnique(count)`
   - `strict=false`：文本不存在返回 `false`，多处匹配替换全部

4. **执行替换** - `src/fs/io.rs:122`
   - 使用 `String::replace(old_text, new_text)` 进行替换（全局替换）
   - 返回新内容字符串

5. **原子写入** - `src/fs/io.rs:125`
   - 调用 `atomic::atomic_write()` 委托给核心模块
   - 确保整个替换操作事务性：读 → 替换 → 原子写

### 3.3 追加写入流程（atomic_append）

1. **读取现有内容** - `src/fs/atomic.rs:81-85`
   - 若文件存在调用 `std::fs::read()`，否则使用空向量

2. **拼接内容** - `src/fs/atomic.rs:87-88`
   - 使用 `extend_from_slice()` 将新内容追加到缓冲区

3. **原子写入** - `src/fs/atomic.rs:90`
   - 调用 `atomic_write(&combined)` 写入完整内容

### 3.4 权限保留流程（atomic_write_preserve_perms）

1. **保存原权限** - `src/fs/atomic.rs:63`
   - 调用 `path.metadata().ok()` 获取原文件元数据（若存在）
   - 提取 `permissions()` 字段

2. **执行原子写** - `src/fs/atomic.rs:66`
   - 委托给 `atomic_write()`

3. **权限恢复** - `src/fs/atomic.rs:70`
   - 使用 `std::fs::set_permissions()` 恢复原权限
   - **注意：** 此步骤本身不是原子的，但在实践中权限变更罕见

## 4. 同文件系统原子性保证

### 4.1 为什么临时文件必须与目标同目录？

```
场景1: 同文件系统 (✓)
  /tmp/target.txt (目标)
  /tmp/.tmp12345 (临时)
  rename(.tmp12345, target.txt) → 原子性保证 ✓

场景2: 跨文件系统 (✗)
  /home/target.txt (目标)
  /tmp/.tmp12345 (临时在 /tmp)
  rename(.tmp12345, /home/target.txt) → 可能复制后删除，非原子 ✗
```

代码实现：`src/fs/atomic.rs:37` 使用 `new_in(dir)` 而非 `new_in(TempDir)` 确保临时文件位置。

### 4.2 POSIX 原子性保证

在 POSIX 兼容系统（Linux、macOS）上：
- `rename()` 是原子内核操作
- 任何观察者要么看到旧文件，要么看到新文件，不会看到中间状态
- 即使进程在 `rename()` 系统调用中被终止，内核也会完成操作

### 4.3 Windows 支持

- `tempfile` crate 在 Windows 上使用 `ReplaceFileW()` API
- 提供等价的原子替换语义（新文件替换旧文件）

## 5. 错误处理与恢复

### 5.1 故障点分析

| 阶段 | 故障 | 结果 | 恢复 |
|------|------|------|------|
| 创建临时文件 | 权限拒绝 | 抛出 `Io` 错误 | 无；原文件不受影响 |
| 写入内容 | I/O 错误 | 抛出 `Io` 错误 | 临时文件被自动清理 |
| fsync 调用 | 磁盘满 | 抛出 `Io` 错误 | 临时文件被自动清理 |
| rename 系统调用 | 失败 | 返回 `persist()` 错误 | 临时文件被自动清理 |
| **rename 完成后** | **任何故障** | **✓ 安全** | 新文件已持久化，原文件已被替换 |

### 5.2 临时文件清理机制

`tempfile::NamedTempFile` 实现 `Drop` trait：
- 若文件从未调用 `persist()`，Drop 时自动删除
- 提供自动清理，无需手动 cleanup 代码
- 若 `persist()` 成功，文件所有权转移，不再被清理

### 5.3 错误转换

`src/fs/atomic.rs:46-51` 将 `persist()` 错误封装为 `AgentGearError::Io`：
```rust
temp_file.persist(path).map_err(|e| {
    AgentGearError::Io(std::io::Error::new(...))
})?
```

## 6. GIL 管理

### 6.1 读写操作的 GIL 释放

`src/fs/io.rs:74-76`（write_file）：
```rust
py.allow_threads(|| super::atomic::atomic_write(path, content.as_bytes()))
```

`src/fs/io.rs:97` （edit_replace）：
```rust
py.allow_threads(|| -> Result<bool> {
    // 读取、检查、替换、写入全部在 GIL 释放状态
})
```

**含义：**
- 允许 Python 解释器在写入期间执行其他线程代码
- 不会阻塞 GIL，提高多线程应用的并发度

## 7. 性能特征

### 7.1 时间复杂度

| 操作 | 时间复杂度 | 主要开销 |
|------|-----------|--------|
| `atomic_write` | O(n) | fsync 磁盘 I/O |
| `edit_replace` | O(n) | 读文件 + 匹配计数 + 替换 + fsync |
| `atomic_append` | O(n) | 读整个文件 + 拼接 + fsync |

其中 n 为文件大小（字节数）。

### 7.2 fsync 开销

- 磁盘 fsync：通常 1-100ms（取决于磁盘类型和系统负载）
- 固态硬盘 (SSD)：通常 < 10ms
- 机械硬盘 (HDD)：通常 5-50ms
- 网络文件系统 (NFS)：可能 > 100ms

**优化机会：**
- 批量 fsync（多个文件一起写）
- 配置 fsync 策略（如可选的非强制同步）
- 使用数据库事务日志模式

## 8. 使用约束

### 8.1 UTF-8 编码

- `write_file` 假设内容为 UTF-8 字符串
- `edit_replace` 对 UTF-8 文本进行模式匹配
- **限制：** 无法处理二进制文件或其他编码（如 UTF-16）

### 8.2 内存限制

- 整个文件必须加载到内存（读操作）
- 大文件（> 1GB）可能导致 OOM
- **未来方向：** 流式操作（`read_file_range` 已预留但未暴露）

### 8.3 并发安全性

- 无内置文件锁机制
- 多个进程同时写同一文件可能产生竞争条件
- **应用层责任：** 使用互斥锁、文件锁或单一写入器模式

## 9. 测试覆盖

`src/fs/atomic.rs:108-161` 包含四个单元测试：

| 测试 | 用例 |
|------|------|
| `test_atomic_write` | 创建新文件并验证内容 |
| `test_atomic_write_overwrite` | 覆盖现有文件 |
| `test_atomic_write_creates_directory` | 自动创建父目录 |
| `test_atomic_append` | 追加内容到现有文件 |

`src/fs/io.rs:170-251` 包含 4 个集成测试：
- 读写循环
- 单一唯一匹配替换
- strict 模式文本不存在处理
- strict 模式多处匹配处理

## 10. 扩展函数地图

### 10.1 已实现（部分暴露）

| 函数 | 暴露状态 | 用途 |
|------|--------|------|
| `atomic_write` | ✓ 间接（通过 write_file） | 核心原子写入 |
| `atomic_write_preserve_perms` | ✗ | 保留权限的写入 |
| `atomic_append` | ✗ | 原子追加 |
| `create_backup` | ✗ | 创建 .bak 备份 |

### 10.2 标记为未暴露的原因

```rust
#[allow(dead_code)]
pub fn atomic_write_preserve_perms(...) { ... }
```

表示函数已实现但未在 Python API 中暴露，可用于：
- 未来扩展
- 内部使用
- 实验性功能

## 11. 设计决策

### 11.1 为什么选择 temp→fsync→rename？

1. **可靠性：** 三步模式在所有现代文件系统上都有明确的失败语义
2. **简洁性：** 不依赖高级锁机制或事务日志
3. **可移植性：** POSIX + Windows 都支持
4. **可观察性：** 中间状态对外不可见（临时文件是隐藏的）

### 11.2 为什么不用文件锁？

- 跨平台支持复杂（fcntl vs Windows locks）
- 不能防护进程崩溃中的部分写入
- 原子 rename 更高效

### 11.3 fsync 的必要性

- Page Cache 异步写回可能很慢（可达 30 秒）
- 关键数据需要立即持久化
- 权衡：必要但有性能代价

---

**最后更新：** 2025-11-29 | 文档版本：1.0
