# Trellis Lite 变更日志

> 配套文档：[README](../README.md) · [usage-guide](usage-guide.md) · [design](design.md) · [exit-codes](exit-codes.md)

本文档记录 Trellis Lite 面向用户的**可观测变更**（新功能、行为变更、修复、破坏性变化）。
源码重构、测试工具调整等不影响最终用户的修改不在此列出。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

---

## [Unreleased] - 2026-07-26

### ⚠ 破坏性变更
- **`task create` 已有活跃任务时拒绝（返回 1）**：之前是"警告 + 继续并替换活跃指针"，用户容易"丢了任务"。新行为遵循"one task at a time"硬规则 —
  - 默认：拒绝 + exit 1 + 文件夹**不创建**
  - 显式接管：传 `--replace` 强制接管
- **现存 `task create` 调用**：如果依赖"警告后继续创建"，需先 `task finish` / `task cancel` 旧任务，或在 create 命令加 `--replace`。

### 修复
- **`task finish` 在 `task.json` 损坏或缺失时不再悄悄崩溃 + 误清活跃指针**：之前如果 `task.json` 损坏，`read_json` 返 `{}` 后 `data["status"] = "done"` 触发 `AttributeError`，但 `clear_current_task()` 仍然执行 → 任务被默默"吃掉"。新行为：严格解析 + 缺失/损坏/空数据均拒绝 + 显式提示 `trellis.py doctor --fix` 修复，活跃指针保留。
- **`session --commit` 不合法格式改为拒绝（exit 1）**：之前是 warn + 静默丢弃 commit 字段（journal 正常写入），新行为：识别为拼写错误会污染未来的 journal 检索，因此拒绝整个 session 写入 + exit 1。
- **任务状态机真正生效（`set_status` 现在拒绝非法转移）**：之前 `ALLOWED_TRANSITIONS` 注释承诺了"forward-only"但代码只检查目标状态是否合法（如 `done → in_progress` 这样的回滚原本能成功）。新行为：`set_status` 同时校验转移合法性，archive/cancelled 终态不可再转移；`done → cancelled` 显式允许（用户改主意）。内部用 `read_json_strict` 替代 `read_json` + 内联解析，丢失数据 vs 缺失文件的语义更清晰。
- **`doctor --fix` 不再把已修复的 warning 留在 summary 列表里**：之前 `--fix` 只在 `problems` 路径 pop，新行为：warnings 路径同样 pop（`tasks/archive/` 等子目录、`workspace/<dev>`、`journal-1.md` 自动创建后），summary 现在能正确反映"已修好"。
- **`doctor` 新增 journal 内部间隔检测**：之前只检查编号是否从 1 开始，现在扫描相邻 journal-N.md 之间的 gap（如 `1, 3, 5` 提示"手动删除 / 部分轮转"）。
- **`task start` 在任务已 `in_progress` 时不再报误导性"corrupted"警告**：之前 `set_status` 对同状态返回 `False`（因为 `ALLOWED_TRANSITIONS` 不含自身），调用方把所有 `False` 统一解释为"task.json missing or corrupted"。新行为：`set_status` 幂等化（同状态返回 `True`，不重写文件、不更新时间戳）；`_task_start` 预检当前状态，对已激活任务输出友好提示 `Note: 'xxx' is already in_progress.`。
- **`uninstall.sh` 清理 `.gitignore` 时不再残留后续条目（用户编辑保护）**：之前 awk 的 `skip=0` 默认规则会在每个非 `.trellis-lite/.X` 行上重置跳过标志，导致用户在标记块内插入注释/空行后，后面跟着的 `.trellis-lite/.X` 行不会被删除（如 `.trellis-lite/.current-task` 残留）。新行为：skip 在用户内容行（注释/空行/其它规则）上保持为 1，只在遇上下一个 `# Trellis Lite runtime` 标记或非 Trellis 区时才隐式重置——可以跨中间用户行清理同一标记块内的所有 `.trellis-lite/.X` 条目。
- **`uninstall.sh` 检测 `.gitignore` marker 时不再被散文文本误触发**：之前 `grep -q "# Trellis Lite runtime"` 不锚定，用户在注释中提到该字符串（如 `# Trellis Lite runtime monitoring explained`）会误入清理分支并输出"removed Trellis Lite runtime entries"误导消息（实际什么都没动）。新行为：`grep -qxF` 镋定整行 + 字面匹配，只有真正的 marker 行才会触发清理。
- **`uninstall.sh` mktemp 临时文件现在在退出时清理**：之前 `tmpfile=$(mktemp)` 后若 awk 失败（极罕见但理论上可能）则 `&&` 链不执行 `mv`，tmpfile 残留在 `/tmp`。新行为：增加 `trap 'rm -f "$tmpfile" 2>/dev/null || true' EXIT` 保证 EXIT 时清理。
- **`install.sh` 重装不再静默覆盖已有 `.developer`**：之前重复运行 install.sh 到同一项目时 `init` 会无条件覆盖 `.developer`（用户原本手工指定的 dev name 被静默替换）。新行为：如果 `.trellis-lite/.developer` 已存在，install 跳过 init 步骤并输出 `Note: .developer already set to '...'; skipping init (re-run 'init' to change).`。需要手动改 dev name 时仍可显式调用 `trellis.py init`。

### 改进（第 4 轮 oracle-reviewer）
- **`session --commit` 现在接受 4–64 位 hex SHA**：之前正则锚定 4–40 位 hex，仅支持 SHA-1。Git 2.42+ 引入 SHA-256 作为默认哈希算法后，commit 字段被误判为"格式错误"拒绝写入。新行为：regex 改为 `^[0-9a-f]{4,64}$`，同时支持 SHA-1 (40) 和 SHA-256 (64)；错误提示同步更新。
- **`task start` 的 in-progress 冲突警告改为汇总单条**：之前 N 个其他 in_progress 任务输出 N 行 `Warning: '...' is still in_progress`；新行为：扫一遍 tasks/ 收集冲突列表，输出**单条**汇总 warning（含计数 + 全部冲突任务名 + 清理建议），减少视觉噪音同时保留全部信息。
- **`resolve_task_dir` 现在用异常信号歧义与缺失**：之前把两种错误都塞进 `return None` + 各自打印，调用方需要再手打一次 `Task not found: ...`（导致重复消息）。新行为：拆为 `AmbiguousTaskName(Exception)`（携带候选列表）和 `FileNotFoundError`，新增 `resolve_or_report()` 包装函数集中翻译为用户消息；`_task_start` / `_task_archive` / `_task_cancel` / `_task_delete` 4 个调用方都改用包装函数，删除冗余的 `Task not found` 行。
- **`cmd_doctor` 删去死代码 try/except**：原本早退分支的 `try/except Exception` 是为了让 `_check_trellis_present` 的 "missing" 信息统一走 problems 列表，但实际上下游检查已经处理该路径。新行为：直接调用 `get_repo_root(init_ok=True)`，依赖 `_check_trellis_present` 统一报告，少 4 行嵌套结构。
- **`_task_delete` 状态判断改用直接比较**：之前 `if status not in ("cancelled",)`（一个元素的元组，可读性差 + 容易被误改成 `(cancelled, archived)`）；新行为：`if status != "cancelled"`，与设计意图一致。

### 文档
- `best-practices.md` 修正第 16 节"决策清单"中"CLI 已会拒绝多 in_progress"的描述：实际 CLI 只 Warning + 返 0，由人工自律。`--replace` 描述同步修正（显式接管，不是替换同名任务）。
- README.md / usage-guide.md / design.md / best-practices.md 同步：测试数量 112 → 123；行数 906 → 1100+；子命令清单加 `task delete` / `version` / `doctor` / `task list --all`。
- 运行测试命令修正：之前 `python3 -m unittest discover -s lite/tests -t .` 在 Python 3.9+ 相对 import 失败；改为 `python3 -m unittest tests.test_*`。
- AGENTS.md 命令清单补全 `task delete` / `doctor` / `version`。
- `exit-codes.md` 新增"退出码不对称 rationale"章节：解释 `task finish` 在 `task.json` 损坏时返回 1（不可逆，须中止）vs `start` / `archive` / `cancel` 返回 0（可恢复，降级继续）的设计依据。
- `docs/design.md` 任务系统小节补"时间戳约定"：明确 `created` / `started` / `finished` / `archived` / `cancelled` 各自对应哪个事件；解释 `planning` 任务**没有** `started` 字段是正确语义。
- `install.sh` --help / 输出现范补"重装语义"：说明重装不会覆盖已有 `.developer`、AGENTS.md、CLAUDE.md、.clinerules/、.gitignore runtime 条目、pre-commit hook，仅在目标未安装时执行初始化动作。

### 测试
- `TestUninstall` 5 个新测试覆盖 `uninstall.sh` 的 `.gitignore` 清理与 pre-commit hook 移除路径（含 O9 补充覆盖 + O11 回归保护：用户在 `.gitignore` 标记块内插入注释/空行后，uninstall 仍能完全清理所有 `.trellis-lite/.X` 条目）。
- `TestUninstall` + `TestInstall` 新增 3 个 O14/O16 测试：`test_uninstall_ignores_non_marker_mentions`（散文 marker 不误触发清理）、`test_install_preserves_existing_developer_on_reinstall`（重装保留 dev name）；`TestUninstall.setUp` O17 增强：git init 失败时 `self.skipTest()` 避免 false-positive。测试总数 116 → 123。

---

## [0.6.9] - 2026-07-26

### 新增
- **`task delete <name>`** 子命令，永久删除任务目录（仅允许 `cancelled` 状态；用 `--force` 跳过状态校验）（`4c777e6`）
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

[Unreleased]: #unreleased---2026-07-26
[0.6.9]: #069---2026-07-26
[0.6.0]: #060---2026-07-12
