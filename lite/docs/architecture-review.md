# Trellis Lite 架构审查记录

> 配套文档：[README](../README.md) · [usage-guide](usage-guide.md) · [design](design.md) · [best-practices](best-practices.md) · [exit-codes](exit-codes.md)

本文档记录 Trellis Lite 在每个发布周期进行的**架构审查**结果与改进计划。
作用：
1. 让未来的 agent 不需要重新发现本已发现的问题
2. 让用户/审阅者知道"为什么这样设计"是经过权衡的
3. 提供一个可追溯的"债务清单"

---

## 2026-07-26 审查（第 5 轮）

### 范围

- 被审查对象：`lite/` 目录（单文件 Python CLI 1100+ 行 + install.sh 244 行 + uninstall.sh + 104 个 unittest + 6 份 markdown 文档）
- 审查维度：功能正确性 / 跨 command 的一致性 / 设计的合理性
- 方法：代码轴面逐函数读 + 文档交叉对比 + 状态机建模；动态测试 104 个全绿

### 已采纳并实施

✅ **F1**：`_task_finish` 在 `task.json` 损坏/缺失/空数据时改为**显式拒绝**（exit 1），不再悄悄崩溃 + 误清活跃指针。
- 触发：`_task_finish` 用 `json.loads` 严格解析（之前 `read_json` 返 `{}` → AttributeError → clear_current_task 仍跑 → 任务被吃掉）
- 修复：3 种损坏情形（missing / JSONDecodeError / 空 dict）均拒绝 + 提示 `doctor --fix`
- 测试：新增 2 个 test，覆盖 3 种损坏路径

✅ **F3**：`_task_create` 已有活跃任务时改为**拒绝**（exit 1），新增 `--replace` 标志显式接管。
- 触发：原"警告 + 替换"导致"任务被悄悄吃掉"风险
- 修复：活跃任务存在时**先检查再 mkdir**（任何 disk mutation 之前），拒绝则文件夹不创建
- 测试：新增 `test_create_replace_takeover_sets_new_current`，更新 2 个旧测试

✅ **F4**：文档一致性。
- 测试数量 41 → 74（README.md / usage-guide.md / design.md / best-practices.md）
- README.md "CLI 命令参考" 补 `task delete` / `version` / `doctor` / `task list --all`
- README.md / usage-guide.md 运行命令修正（之前 `discover -s lite/tests -t .` 在 Python 3.9+ 相对 import 失败）
- CHANGELOG.md 新增 [Unreleased] 章节，标 F1 + F3 为 Breaking Change
- CHANGELOG.md `task delete` 描述纠正（之前写"允许 cancelled/archived"，实际只允许 cancelled）

✅ **F6**：状态机集中化。
- 新增 `STATUSES: frozenset[str]` + `ALLOWED_TRANSITIONS: dict[str, frozenset[str]]` 常量
- 新增 `set_status(task_dir, new_status, *, when=None) -> bool` helper，严格解析 + 缺失/损坏/空数据均拒绝
- 替换 5 处内联 `data["status"] = "..."` 赋值为 helper 调用
- 测试：新增 `test_status_machine.py` 14 个测试（7 个常量 + 7 个 helper）

✅ **F8**：`cmd_doctor` 拆分。
- `cmd_doctor` 由 134 行单体拆为编排函数 + 9 个 `check_<thing>()` 子函数（`_check_trellis_present` / `_check_developer_file` / `_check_required_subdirs` / `_check_workspace_dir` / `_check_current_task` / `_check_task_integrity` / `_check_journal_numbering` / `_check_python_version` / `_check_working_tree`）
- 编排函数变为 ~30 行的顺序执行，每个 check 独立可测
- 测试：8 个 doctor 测试无修改全部通过（输出字符串契约保留）

✅ **F9**：journal 解析 / 旋转集中化。
- 新增 `list_journals(workspace) -> list[tuple[int, Path]]` 与 `rotate_if_full(workspace, journals) -> Path` helper
- 替换 4 处内联 journal 枚举逻辑：`cmd_session`、`cmd_context`、`cmd_doctor` workspace 检查、`cmd_doctor` 编号间隔检查
- 总共减少 ~30 行重复代码

✅ **F2**：Usage 错误信息集中化。
- 新增 `USAGE: dict[str, str]` 字典（8 个命令键）+ `usage_for(key)` helper
- 替换 9 处内联 `print(colored("Usage: ...", C_RED))` 调用
- 测试：新增 `test_usage_consistency.py` 15 个测试（5 个字典结构 + 2 个 helper + 8 个端到端），未来新命令忘了注册会立即失败

✅ **F7**：`session --commit` 校验失败时改为**拒绝（exit 1）**，不再 warn + 静默丢弃。
- 触发：原行为让拼写错误污染 journal 检索（写入了一条"假 commit"的 session）
- 修复：识别为拼写错误拒绝整个 session 写入 + exit 1
- 测试：原 `test_session_warns_on_bad_commit_and_drops` → 拆为 `test_session_rejects_bad_commit` + `test_session_accepts_various_valid_shas`（覆盖 4-char / 8-char / 16-char / 40-char）

### 保留（暂不做）

- ⏸ **F5**（三套 cwd 假设）：`cmd_session` / `cmd_context` / `cmd_doctor` 用 `get_repo_root()` 路径不一致。**未处理**（影响小，且各 command 独立可工作）。
- ⏸ **F10**（`cmd_context` 88 行）：拆 6 个章节函数。**未处理**（与 F8 类似收益，但当前 88 行仍可读）。
- ⏸ **F11**（`_task_create` 不写 `started` 字段）：状态字段语义不一致。**待定**（需要更明确的语义讨论）。
- ⏸ **F12**（重复 F7）— 已被 F7 覆盖。
- ⏸ **F13**（doctor 提示不准）：低优先。

### 拒绝（不会做）

- ❌ 拆分单文件为包：违反 "1 文件搞定一切" 核心原则。
- ❌ 引入 SQLite：违反"零依赖" + 失去 human-readable 优势。
- ❌ 改 `argparse` 重写 CLI：当前 if/elif 在 8 个子命令下可读性尚可。
- ❌ 真任务级 spec 自动 inline：需要 schema 改造，4h+，当前 AI 每次调 `specs` 列出已够用。
- ❌ 多 developer 并存：超出 Lite 单人定位。
- ❌ 国际化 / i18n：当前 zh/en 一致；切换需要先抽 `messages.py`。

### 验证

- **104 个 unittest 全部通过**（F1 +2, F3 +1, F6 +14, F2 +15, F7 +1 +1 -1 = +32）
- 行数：1122 → 1280（净增 +158；新常量 + helper，但 30 行重复 journal 逻辑抵消）
- 现有 8 个 doctor 测试无修改全部通过（输出字符串契约保留）

---

## 审查方法论（回顾）

### 审查维度

1. **功能正确性**：每个 command 行为是否与文档一致；失败路径是否合理
2. **连贯性**：跨 command 是否一致（错误码、状态机、错误处理、退出信息）
3. **合理性**：抽象层次、模块边界、是否过度设计或欠设计

### 证据收集

- 函数长度 + 状态变化映射（status 字段在哪赋值）
- 错误信息文本（Usage / Warning / Error 等 8 处）
- 文档间事实交叉（README ↔ usage-guide ↔ CHANGELOG ↔ design ↔ best-practices）
- 隐式契约（`read_json` 返 `{}` 让多个写操作都易出 bug）

### 输出 contract

- 优先级发现（带文件/子系统证据、影响、置信度）
- 分阶段计划（范围、收益、依赖、验证）
- 保留 / 推迟 / 拒绝的明确清单
- 开放决策（需要用户拍板的方向）

---

## 审查清单（每次发布前回顾）

- [ ] **F5** ❓ 决定 `cwd` 一致性的最终处理（统一 helper 还是按场景分别处理）
- [ ] **F10** ❓ `cmd_context` 是否也走类似 F8 的拆分
- [ ] **F11** ❓ `_task_create` 是否补 `started` 字段
- [ ] 检查新代码是否引入新的"分散赋值"或"重复逻辑"
- [ ] 检查新增 test 是否覆盖了失败路径（损坏、缺失、并发）
- [ ] 检查新命令是否在 `USAGE` 字典 + `USAGE.test_all_expected_command_keys_present` 都注册了

---

## 历史审查

- 2026-07-26 — 第 5 轮（本文档）
- 2026-07-12 — 第 4 轮（见 git log `feat: fourth-round UX enhancements`）
- 2026-07-08 — 第 3 轮（流程审查，commit 4154cb089519）
- 2026-06-30 — 第 2 轮（质量审查，PR/issue 计数待补）
- 2026-06-15 — 第 1 轮（首版审查，commit f94d2d1）
