# Trellis Lite 变更日志

> 配套文档：[README](../README.md) · [usage-guide](usage-guide.md) · [design](design.md) · [exit-codes](exit-codes.md)

本文档记录 Trellis Lite 面向用户的**可观测变更**（新功能、行为变更、修复、破坏性变化）。
源码重构、测试工具调整等不影响最终用户的修改不在此列出。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

---

## [0.6.9] - 2026-07-26

### 新增
- **`task delete <name>`** 子命令，删除单个任务（仅允许 `cancelled`/`archived` 状态；用 `--force` 跳过状态校验）（`4c777e6`）
- **`version`** 子命令，打印 `trellis-lite 0.6.9`；`__version__` 作为唯一真实来源（`689a660`）
- **`doctor [--fix]`** 诊断命令，自检 9 项（`.trellis-lite/` 存在、`.developer`、子目录、workspace、`.current-task`、任务完整性、journal 编号、Python 版本、git 脏文件）；`--fix` 自动修复大部分问题（`当前提交`）
- **`lite/hooks/pre-commit`** Git pre-commit hook：commit 前跑 `doctor` + 提醒 planning 状态任务；`install.sh` 在 `.git/` 存在时自动安装（`当前提交`）
- **`SPEC_TEMPLATE` 外置化**：默认模板从内嵌字符串改为 `.trellis-lite/spec/TEMPLATE.md`（`689a660`）
- **spec link 提示**：`specs` 命令在找不到 `.trellis-lite/spec/` 时提示用户创建并链接模板
- **`uninstall.sh`** 一键卸载脚本（`40a715a`）
- **`exit-codes.md`** 文档：C0 / C1 / C2 退出码约定及 shell/CI 用法（`当前提交`）
- **CI**：GitHub Actions 在 5 个 Python 版本（3.9–3.13）+ uninstall.sh 烟测 + coverage 报告（`40a715a` / `557c6aa`）

### 修复
- **`get_repo_root()`** 找不到 `.trellis-lite/` 时不再静默返回 cwd，改为打印错误并 `exit 1`，避免误写目录（`40a715a`）
- **`task finish` 在无活跃任务时返回 1**（之前是 0），符合"用户错误应该非零退出"的约定（`40a715a`）
- **`install.sh`** 在 `.trellis-lite/` 已存在时不再误覆盖；同时清理模板拷贝里残留的 `.current-task` / `.developer`（`90eccdf` 之前）

### 文档
- `best-practices.md` 和 `workflow-checklist.md`（`4f3a4c8` / `ab6f6be`）

### 测试
- 41 单元测试 + GitHub Actions CI（`fb52ce67`）
- 单元测试总数从 41 增加到 **71**（含 8 个 doctor 测试 + 3 个 pre-commit hook 测试 + 1 个 slugify fuzz + 8 个边界测试）

---

## [0.6.0] - 2026-07-12

### 新增
- **Trellis Lite 首发**：单文件 Python 替代 20+ 脚本，零运行时依赖，要求 Python 3.9+
- **核心命令**：`init`、`task create/start/current/finish/archive/cancel/list`、`session`、`context`、`specs`
- **`install.sh`** 安装脚本，支持 Qoder / Claude Code / OpenCode / Cline 四平台同步安装
- **模板系统**：`.trellis-lite/spec/*.md` 为 AI 提供 per-package / per-layer 编码规约
- **3-Phase Workflow**：PLAN → CODE → WRAP，由 `task` 状态机驱动

---

## 维护说明

### 自动生成

`CHANGELOG.md` 当前由人工维护（更适合小项目 + 强可读性）。

当 commit 数量变多、需要自动化时，推荐方案：

```bash
# 1. 列出上次发布后的提交（按 conventional commit 前缀分组）
git log <last-tag>..HEAD --pretty=format:"%s" | grep -E "^(feat|fix|docs|chore|test|refactor)"
```

未来若引入 `git-cliff` 或 `auto-changelog`，可生成基础版本后再人工编辑。

### 提交合并策略

每个版本（每个 `0.x.y`）对应**至少一个语义化的提交流**：

| 标签 | 含义 | 例子 |
|---|---|---|
| `feat(...)` | 用户可见的新功能 | `feat(task-delete): new subcommand` |
| `fix(...)` | 用户可见的 bug 修复 | `fix(hardening): exit-code consistency` |
| `docs(...)` | 文档、注释 | `docs: add best-practices.md` |
| `test(...)` | 测试新增 | `test(slugify-fuzz): adversarial testing` |
| `chore(...)` | 工具、CI | `ci(coverage): report metric` |
| `refactor(...)` | 内部重构，不影响外部行为 | _通常不写入 CHANGELOG_ |

### 发布 checklist

每次发布新版本 `0.x.y` 时：

1. 更新 [`trellis.py`](../.trellis-lite/scripts/trellis.py) 里的 `__version__ = "0.x.y"`
2. 更新 [`README.md`](../README.md) 顶部版本号（如有）
3. 在 `CHANGELOG.md` **顶部**添加新章节，把待发布版本的改动归类后列出
4. 跑 `python3 -m unittest tests.test_init tests.test_install tests.test_precommit tests.test_session tests.test_slugify_fuzz tests.test_task tests.test_doctor tests.test_context_specs_help` 确认全绿
5. `git tag 0.x.y` 并 `git push --tags`

### 不放进 CHANGELOG 的内容

- 内部重构（除非改外部行为）
- 测试工具调整
- 注释、空白
- 依赖升级（除非影响用户）

---

[0.6.9]: #069---2026-07-26
[0.6.0]: #060---2026-07-12
