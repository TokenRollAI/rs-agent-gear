# Changelog

## [0.1.0] - 2024-11-29

### Added

#### Core Features (Phase 1)
- **FileSystem** class - 高性能文件系统接口
- **list()** / **glob()** - 内存索引文件列表，支持 glob 模式
- **read_file()** - 单文件读取
- **read_batch()** - Rayon 并行批量读取
- **write_file()** - 原子写入 (temp→fsync→rename)
- **edit_replace()** - 文本替换，支持 strict 模式
- **grep()** - 高性能内容搜索，支持正则表达式
- **get_metadata()** - 获取文件元信息

#### File Watching (Phase 2)
- **FileWatcher** - 跨平台文件监听 (inotify/FSEvents/ReadDirectoryChanges)
- **Debouncer** - 100ms 事件防抖动
- **索引增量更新** - 自动同步 Create/Modify/Delete/Rename 事件
- **is_watching()** - 检查监听状态

#### Performance Optimizations
- `**/*` 快速路径 - 跳过 glob 匹配
- Rayon 并行 - list/glob/grep 全部并行化
- mmap 大文件 - 超过 32KB 使用内存映射
- 索引复用 - grep 使用预构建的文件列表
- relative_path 优化 - 避免不必要的字符串拷贝

### Performance (10000 files benchmark)

| Operation | Agent-Gear | Python stdlib | Speedup |
|-----------|------------|---------------|---------|
| list | 2.83ms | 8.00ms | 2.8x |
| glob | 2.88ms | 14.35ms | 5.0x |
| grep | 4.71ms | 53.27ms | 11.3x |

### Technical Details
- Python 3.12+ (abi3-py312)
- Rust 1.75+
- PyO3 0.23 bindings
- DashMap concurrent index
- Rayon data parallelism
- notify crate for file watching

## Planned

### Phase 3: Advanced Features
- [ ] 大文件流式读取
- [ ] Python async/await 支持
- [ ] grep context_lines 参数
- [ ] 文件内容缓存

### Optimizations
- [ ] batch_read 小文件性能
- [ ] 批量 fsync 优化
