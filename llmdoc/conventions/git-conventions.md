# Git 规范

## 1. 概述

本文档定义了 Agent-Gear 项目的 Git 工作流程规范，包括分支策略、提交消息格式、版本号管理和日常开发流程。

---

## 2. 分支策略

采用基于主干的开发模型（Trunk-Based Development）：

### 主分支

- **`master`**：主分支，始终保持可部署状态
  - 只接收来自 `develop` 分支的合并请求
  - 每个合并必须对应一个版本发布
  - 需要代码审核和 CI/CD 通过

### 开发分支

- **`develop`**：开发分支，集成测试分支
  - 基于最新的 `master` 创建新功能分支
  - 开发完成后向 `develop` 提交 PR
  - 所有功能分支最终汇总至此

### 功能/修复分支

命名规则：`<type>/<issue-id>-<short-description>`

**类型包括：**

- `feature/` - 新功能
- `fix/` - Bug 修复
- `chore/` - 维护任务
- `docs/` - 文档更新
- `refactor/` - 重构
- `test/` - 测试相关

**示例：**

```
feature/GH-123-parallel-batch-read
fix/GH-456-memory-leak-in-indexer
docs/update-api-reference
```

### 分支生命周期

1. 从 `develop` 创建功能分支
2. 在本地开发和提交
3. 推送到远程并创建 PR
4. 通过审核和 CI 检查
5. Squash merge 至 `develop`
6. 删除特性分支

---

## 3. 提交消息格式

遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范。

### 基本格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### 类型（Type）

- **feat:** 新功能
- **fix:** Bug 修复
- **docs:** 文档更新
- **style:** 格式调整（不影响代码逻辑）
- **refactor:** 代码重构
- **perf:** 性能优化
- **test:** 测试相关
- **chore:** 构建、依赖等维护任务
- **ci:** CI/CD 配置更改

### 作用域（Scope）

- `fs` - 文件系统操作
- `indexer` - 索引系统
- `search` - 搜索功能
- `bindings` - Python/Rust 绑定
- `build` - 构建系统
- `ci` - CI/CD 配置
- `docs` - 文档

### 主题（Subject）

- 使用祈使语气（"add" 而非 "added"）
- 首字母小写
- 不以句号结尾
- 限制在 50 字符以内

### 正文（Body）

- 解释 **为什么** 而非 **是什么**
- 每行 72 字符换行
- 分离标题和正文的空行

### 页脚（Footer）

- 关联 Issue：`Closes #123`
- Breaking changes：`BREAKING CHANGE: ...`
- Co-Authored-By：`Co-Authored-By: Name <email>`

### 示例提交

```
feat(fs): implement async batch read operations

Add support for parallel file reading using tokio runtime.
Improves performance for large batch operations.

- Use DashMap for concurrent state management
- Implement proper error aggregation
- Add benchmarks showing 5x speedup

Closes #456
```

```
fix(indexer): prevent memory leak in watch handler

The file watcher was holding references to old file trees
in memory. Now properly releases them after refresh.

Closes #789
```

---

## 4. 版本号管理

遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范：`MAJOR.MINOR.PATCH`

### 版本号规则

- **MAJOR** - 不兼容的 API 变化
- **MINOR** - 新增功能（向后兼容）
- **PATCH** - Bug 修复（向后兼容）

### 预发布版本

- Alpha：`0.1.0-alpha.1`
- Beta：`0.1.0-beta.1`
- Release Candidate：`0.1.0-rc.1`

### 版本发布流程

1. 更新 `Cargo.toml` 和 `pyproject.toml` 中的版本号
2. 在 `CHANGELOG.md` 中记录变更
3. 提交 commit：`chore(release): v0.1.0`
4. 创建 Git tag：`git tag -a v0.1.0 -m "Release v0.1.0"`
5. 推送 tag：`git push origin v0.1.0`
6. CI/CD 自动构建并发布

### 当前版本

见 `Cargo.toml` 和 `pyproject.toml`：`0.1.0` (Alpha)

---

## 5. 日常开发流程

### 开始新功能

```bash
# 1. 切换到开发分支
git checkout develop
git pull origin develop

# 2. 创建功能分支
git checkout -b feature/GH-123-my-feature

# 3. 在本地开发
# ... 编码 ...
git add .
git commit -m "feat(scope): description"
```

### 提交 Pull Request

```bash
# 1. 推送分支
git push origin feature/GH-123-my-feature

# 2. 在 GitHub 创建 PR
# - 设置 base: develop
# - 填写完整的 PR 描述
# - 关联相关 Issue

# 3. 等待审核和 CI 通过
```

### 合并到主干

```bash
# 1. 确保本地是最新
git checkout develop
git pull origin develop

# 2. Squash merge（保持历史整洁）
git merge --squash feature/GH-123-my-feature
git commit -m "feat(scope): description (Closes #123)"

# 3. 推送
git push origin develop

# 4. 删除远程分支
git push origin --delete feature/GH-123-my-feature

# 5. 删除本地分支
git branch -d feature/GH-123-my-feature
```

### 发布版本

```bash
# 1. 确保 develop 已准备好
git checkout master
git pull origin master

# 2. 创建发布分支
git checkout -b release/v0.2.0

# 3. 更新版本号和 CHANGELOG
# 编辑 Cargo.toml 和 pyproject.toml
# 编辑 CHANGELOG.md

# 4. 提交
git commit -am "chore(release): v0.2.0"

# 5. 合并到 master
git checkout master
git merge --no-ff release/v0.2.0
git tag -a v0.2.0 -m "Release v0.2.0"

# 6. 同步回 develop
git checkout develop
git merge --no-ff release/v0.2.0

# 7. 清理
git branch -d release/v0.2.0

# 8. 推送
git push origin master develop --tags
```

---

## 6. 提交检查清单

提交前务必检查：

- [ ] 代码通过本地测试：`cargo test && pytest tests/`
- [ ] 遵循代码风格：`cargo fmt && ruff check`
- [ ] 提交消息遵循 Conventional Commits 规范
- [ ] 功能分支有明确的作用域和描述
- [ ] 没有提交敏感信息（密钥、密码等）
- [ ] PR 描述完整，关联了对应的 Issue

---

## 7. 常见命令速查

| 任务 | 命令 |
|------|------|
| 创建分支 | `git checkout -b feature/description` |
| 查看分支 | `git branch -a` |
| 切换分支 | `git checkout branch-name` |
| 同步主分支 | `git fetch origin && git rebase origin/master` |
| 查看提交日志 | `git log --oneline --graph --decorate` |
| 撤销最后提交 | `git reset --soft HEAD~1` |
| 修改最后提交 | `git commit --amend` |
| 创建 tag | `git tag -a v0.1.0 -m "message"` |
| 删除远程分支 | `git push origin --delete branch-name` |

---

## 8. 相关资源

- [Conventional Commits](https://www.conventionalcommits.org/)
- [语义化版本](https://semver.org/lang/zh-CN/)
- [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow)
- [Trunk-Based Development](https://trunkbaseddevelopment.com/)
