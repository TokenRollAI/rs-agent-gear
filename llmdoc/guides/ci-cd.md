# CI/CD 流程指南

## 1. 概述

Agent-Gear 项目使用 GitHub Actions 实现自动化的持续集成（CI）和持续发布（CD）流程。本指南说明 CI/CD 工作流的配置、执行方式和故障排查。

---

## 2. CI/CD 工作流概览

### 触发条件

| 工作流 | 文件 | 触发事件 | 目的 |
|------|------|--------|------|
| **CI** | `.github/workflows/ci.yml` | push/PR 到 `master`/`main` | 代码质量检查和测试 |
| **Release** | `.github/workflows/release.yml` | git tag `v*` 或手动触发 | 多平台构建和 PyPI 发布 |

### 执行流程图

```
开发者提交代码
  ↓
Push to develop/feature 分支
  ↓
创建 PR 到 master
  ↓
CI 工作流运行 ──→ 失败 → 修复代码 → 重新提交
  ↓ 通过
代码审核通过，合并到 master
  ↓
创建版本 tag (v0.1.0)
  ↓
推送 tag: git push origin v0.1.0
  ↓
Release 工作流自动触发 ──→ 多平台构建 ──→ PyPI 发布
```

---

## 3. CI 工作流详解

文件位置：`.github/workflows/ci.yml`

### 3.1 Rust 测试矩阵

**运行条件：** push/PR 到 master/main 分支

**测试矩阵：**
```
操作系统: [ubuntu-latest, macos-latest, windows-latest]
```

**执行步骤：**

1. **检出代码**
   ```bash
   actions/checkout@v4
   ```

2. **安装 Rust 工具链**
   - 使用 `dtolnay/rust-action@stable` 安装最新稳定版 Rust
   - 包含组件：`rustfmt`, `clippy`

3. **缓存依赖**
   - 使用 `Swatinem/rust-cache@v2` 加速构建

4. **格式检查**
   ```bash
   cargo fmt --all -- --check
   ```
   - 确保代码符合 Rust 格式规范（见 `conventions/coding-conventions.md`）

5. **Clippy 代码分析**
   ```bash
   cargo clippy --all-targets --all-features -- -D warnings
   ```
   - 运行 Clippy 检查，将所有警告视为错误
   - 禁止 clippy warnings 提交代码

6. **运行单元测试**
   ```bash
   cargo test --all-features
   ```
   - 执行所有 Rust 单元测试

### 3.2 Python 测试矩阵

**运行条件：** push/PR 到 master/main 分支

**测试矩阵：**
```
操作系统: [ubuntu-latest, macos-latest, windows-latest]
Python 版本: ["3.12", "3.13"]
```

**执行步骤：**

1. **检出代码**
   ```bash
   actions/checkout@v4
   ```

2. **安装 Python**
   ```bash
   actions/setup-python@v5
   ```

3. **安装 Rust 工具链**
   ```bash
   dtolnay/rust-action@stable
   ```

4. **缓存 Rust 依赖**
   ```bash
   Swatinem/rust-cache@v2
   ```

5. **安装 maturin**
   ```bash
   pip install maturin
   ```
   - maturin 用于构建 PyO3 扩展

6. **构建并安装扩展**
   ```bash
   maturin develop --release
   ```
   - 编译 Rust 代码生成 Python 扩展
   - `--release` 标志启用优化

7. **安装测试依赖**
   ```bash
   pip install pytest pytest-benchmark
   ```

8. **运行 Python 测试**
   ```bash
   pytest tests/python -v
   ```
   - 执行所有 Python 测试用例

### 3.3 类型检查

**运行条件：** push/PR 到 master/main 分支

**执行步骤：**

1. **安装工具**
   ```bash
   pip install mypy ruff
   ```

2. **Ruff 代码检查**
   ```bash
   ruff check .
   ```
   - 检查 Python 代码的 linting 问题

3. **Ruff 格式检查**
   ```bash
   ruff format --check .
   ```
   - 验证代码格式符合项目规范

---

## 4. Release 工作流详解

文件位置：`.github/workflows/release.yml`

### 4.1 触发条件

**自动触发：**
- 推送 git tag 匹配 `v*` 模式
  ```bash
  git tag -a v0.1.0 -m "Release v0.1.0"
  git push origin v0.1.0
  ```

**手动触发：**
- GitHub Actions 界面手动运行（支持 dry_run 参数）

### 4.2 Linux Wheels 构建

**任务名：** `linux`

**构建矩阵：**
```
- target: x86_64-unknown-linux-gnu (Ubuntu)
- target: aarch64-unknown-linux-gnu (Ubuntu, cross-compilation)
```

**执行步骤：**

1. 检出代码
2. 安装 Python 3.12
3. 使用 `PyO3/maturin-action@v1` 构建 wheels
   - 参数：`--release --out dist`
   - `manylinux: auto` - 自动选择 manylinux 版本
4. 上传构建产物

### 4.3 macOS Wheels 构建

**任务名：** `macos`

**构建矩阵：**
```
- target: x86_64-apple-darwin (Intel macOS 13)
- target: aarch64-apple-darwin (Apple Silicon, macOS 14)
```

**执行步骤：**

1. 检出代码
2. 安装 Python 3.12
3. 使用 `PyO3/maturin-action@v1` 构建 wheels
   - 参数：`--release --out dist`
4. 上传构建产物

### 4.4 Windows Wheels 构建

**任务名：** `windows`

**构建矩阵：**
```
- target: x86_64-pc-windows-msvc
```

**执行步骤：**

1. 检出代码
2. 安装 Python 3.12
3. 使用 `PyO3/maturin-action@v1` 构建 wheels
   - 参数：`--release --out dist`
4. 上传构建产物

### 4.5 源码分发包 (sdist) 构建

**任务名：** `sdist`

**执行步骤：**

1. 检出代码
2. 使用 `PyO3/maturin-action@v1` 构建 sdist
   - 命令：`sdist`
   - 参数：`--out dist`
3. 上传构建产物

### 4.6 发布到 PyPI

**任务名：** `publish`

**执行条件：**
```
needs: [linux, macos, windows, sdist]  # 所有构建任务必须完成
if: startsWith(github.ref, 'refs/tags/') && !inputs.dry_run
```

**发布环境：**
- 使用 `pypi` 环境配置
- PyPI 项目 URL：`https://pypi.org/project/agent-gear`

**权限配置：**
```yaml
permissions:
  id-token: write  # OIDC 发布需要此权限
```

**Trusted Publisher 配置：**

使用 OpenID Connect (OIDC) 进行安全发布，无需存储 API 密钥。

1. **PyPI 侧配置（一次性）：**
   - 访问项目设置：`https://pypi.org/project/agent-gear/settings/`
   - 选择 "Publishing" 标签
   - 添加 Trusted Publisher：
     - Provider: GitHub
     - Workflow: `Release`
     - Ref: `refs/tags/*`

2. **GitHub 侧配置（已完成）：**
   - `.github/workflows/release.yml` 已设置 `id-token: write` 权限
   - 发布步骤使用 `pypa/gh-action-pypi-publish@release/v1`

**发布步骤：**

1. 从所有构建任务下载 artifacts
   ```bash
   actions/download-artifact@v4
   pattern: wheels-*
   path: dist
   merge-multiple: true
   ```

2. 列出分发包内容
   ```bash
   ls -la dist/
   ```

3. 发布到 PyPI
   ```bash
   pypa/gh-action-pypi-publish@release/v1
   verbose: true
   ```

---

## 5. 发布完整流程（开发者指南）

### 5.1 准备发布

1. **确保所有代码已合并到 master**
   ```bash
   git checkout master
   git pull origin master
   ```

2. **更新版本号**
   - 编辑 `Cargo.toml`：更新 `version` 字段
   - 编辑 `pyproject.toml`：更新 `version` 字段
   ```toml
   # Cargo.toml
   [package]
   version = "0.2.0"
   ```

3. **更新 CHANGELOG**
   - 编辑 `CHANGELOG.md`
   - 记录本版本的所有重要变更
   - 遵循 [Keep a Changelog](https://keepachangelog.com/) 格式

4. **提交版本变更**
   ```bash
   git add Cargo.toml pyproject.toml CHANGELOG.md
   git commit -m "chore(release): v0.2.0"
   ```

### 5.2 创建和推送 Tag

```bash
# 创建带注解的 tag
git tag -a v0.2.0 -m "Release v0.2.0"

# 验证 tag
git tag -l -n
# 输出示例：
# v0.1.0  Release v0.1.0
# v0.2.0  Release v0.2.0

# 推送 tag 到远程（触发 Release 工作流）
git push origin v0.2.0
```

### 5.3 监控 Release 工作流

1. **访问 GitHub Actions**
   - 打开 https://github.com/your-org/agent-gear/actions
   - 在 "Workflows" 中选择 "Release"

2. **查看构建进度**
   - 等待所有任务完成：
     - `linux` - x86_64 和 aarch64 wheels
     - `macos` - Intel 和 Apple Silicon wheels
     - `windows` - x86_64 wheels
     - `sdist` - 源码分发包

3. **验证 PyPI 发布**
   - 访问 https://pypi.org/project/agent-gear/
   - 确认新版本已发布
   - 检查文件列表（应包含 6+ wheels + 1 sdist）

### 5.4 故障排查

**CI 测试失败：**
- GitHub Actions 日志显示失败原因
- 修复代码后重新推送 tag：
  ```bash
  # 删除本地 tag
  git tag -d v0.2.0

  # 修复问题、提交、重新创建 tag
  git commit -am "fix: resolve CI failure"
  git tag -a v0.2.0 -m "Release v0.2.0"

  # 强制推送 tag（重新触发 Release）
  git push origin v0.2.0 --force
  ```

**Trusted Publisher 权限错误：**
- 检查 PyPI 是否已配置 Trusted Publisher
- 确认 GitHub Actions 权限：`permissions.id-token: write`
- 重新运行发布任务：GitHub Actions 界面 → Release → 点击 "publish" 任务 → "Re-run job"

**构建超时：**
- 某些平台（如 aarch64）可能需要较长编译时间
- GitHub Actions 默认超时为 6 小时，通常足够
- 检查依赖版本是否过高导致编译变慢

---

## 6. 环境变量和配置

### 环境变量

| 变量 | 值 | 用途 |
|------|-----|------|
| `CARGO_TERM_COLOR` | `always` | 彩色 Rust 编译输出 |
| `PACKAGE_NAME` | `agent-gear` | PyPI 包名 |
| `PYTHON_VERSION` | `3.12` | 构建 wheels 使用的 Python 版本 |

### 配置文件

- **Rust 配置：** `Cargo.toml`
- **Python 配置：** `pyproject.toml`、`pyproject.toml` (maturin 部分)
- **版本号：** 需手动同步 `Cargo.toml` 和 `pyproject.toml`

---

## 7. 最佳实践

### 7.1 本地测试

在推送代码前，确保所有测试本地通过：

```bash
# Rust 测试
cargo test --all-features
cargo clippy --all-targets --all-features -- -D warnings
cargo fmt --all -- --check

# Python 测试
pip install maturin pytest pytest-benchmark
maturin develop --release
pytest tests/python -v

# 代码检查
ruff check .
ruff format --check .
```

### 7.2 提交前检查清单

- [ ] 所有 Rust 测试通过
- [ ] 所有 Python 测试通过
- [ ] 代码格式正确（`cargo fmt`, `ruff format`）
- [ ] Clippy 和 ruff 检查无警告
- [ ] 版本号已更新
- [ ] CHANGELOG 已更新
- [ ] 提交消息遵循 Conventional Commits 规范

### 7.3 跨平台测试

由于 GitHub Actions 在多平台上运行，建议：

1. **修改平台特定代码时** - 特别注意 `src/fs/watcher.rs` 中的 OS 条件编译
2. **使用容器本地测试** - 可以使用 Docker 测试 Linux 构建
3. **监听构建日志** - 某些平台编译问题可能只在 CI 中出现

---

## 8. 相关文件和资源

### 项目文件

- `.github/workflows/ci.yml` - CI 工作流配置
- `.github/workflows/release.yml` - Release 工作流配置
- `Cargo.toml` - Rust 项目配置和版本号
- `pyproject.toml` - Python 项目配置和版本号
- `CHANGELOG.md` - 版本变更日志

### 相关文档

- `conventions/git-conventions.md` - Git 工作流和版本发布规范
- `guides/development.md` - 本地开发环境搭建
- `conventions/coding-conventions.md` - 代码风格和规范

### 外部资源

- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [PyO3 maturin-action](https://github.com/PyO3/maturin-action)
- [PyPI Trusted Publisher](https://docs.pypi.org/trusted-publishers/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [语义化版本](https://semver.org/lang/zh-CN/)

---

## 9. 常见问题解答

**Q: 为什么要使用 Trusted Publisher 而不是 API token？**
A: Trusted Publisher 更安全，避免需要长期有效的 API token 存储在 GitHub 中。使用 OIDC 的短期 token，安全性更高。

**Q: 能否手动触发 Release 工作流？**
A: 可以，通过 GitHub Actions 界面的 "Run workflow" 功能，支持 `dry_run` 参数。

**Q: CI 失败后如何重新发布同一版本？**
A: 修复问题并提交，然后使用 `git push origin tag_name --force` 强制更新 tag 并重新触发 Release。

**Q: 如何跳过发布只进行构建测试？**
A: 使用 GitHub Actions 手动触发，设置 `dry_run: true`。

**Q: 为什么 aarch64 构建耗时特别长？**
A: aarch64 (ARM64) 是通过交叉编译实现的，编译时间比 x86_64 长 2-3 倍。这是正常现象。

---

**最后更新：** 2025-11-30
