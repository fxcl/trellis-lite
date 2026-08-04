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

- 被审查对象：`lite/` 目录（单文件 Python CLI 1300+ 行 + install.sh 244 行 + uninstall.sh + 112 个 unittest + 6 份 markdown 文档）
- 审查维度：功能正确性 / 跨 command 的一致性 / 设计的合理性
- 方法：代码轴面逐函数读 + 文档交叉对比 + 状态机建模；动态测试 112 个全绿

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

- ⏸ **F5**（三套 cwd 假设）：`cmd_context` 是唯一还在用 `get_repo_root()` 拼 `task_dir = repo / current` 的 command（因为 `.current-task` 存的是 repo-relative 字符串）。**已重评**：硬塞统一 helper 反而要加 `removeprefix` 胶水代码，得不偿失。**等 `.current-task` 改存法后自然消解**。
- ❌ **F10**（`cmd_context` 88 行）：**已 DROPPED**。F9 之后已降至 77 行 + 5 个标题注释，是"可读但不过度工程"的甜点；拆 5 个 print 副作用函数不会让单测更好写。
- ❌ **F11**（`_task_create` 不写 `started` 字段）：**已 DROPPED**（被错怪）。`started` = 第一次切到 `in_progress` 的时刻；`planning` 任务上 `started` 不存在是**正确语义**。唯一该做的是 `docs/design.md` 加一行区分 `created` vs `started`，5 分钟。
- ❌ **F12**（重复 F7）— 已被 F7 覆盖。
- ⚠ **F13**（doctor `--fix` 后 warning 残留）：**Grew worse** — F8 拆分暴露了一个回归（`_check_required_subdirs` + `_check_workspace_dir` 修复后没 `warnings.pop()`，导致已修 warning 仍出现在最终摘要）。详见第 6 轮 F19。

### 拒绝（不会做）

- ❌ 拆分单文件为包：违反 "1 文件搞定一切" 核心原则。
- ❌ 引入 SQLite：违反"零依赖" + 失去 human-readable 优势。
- ❌ 改 `argparse` 重写 CLI：当前 if/elif 在 8 个子命令下可读性尚可。
- ❌ 真任务级 spec 自动 inline：需要 schema 改造，4h+，当前 AI 每次调 `specs` 列出已够用。
- ❌ 多 developer 并存：超出 Lite 单人定位。
- ❌ 国际化 / i18n：当前 zh/en 一致；切换需要先抽 `messages.py`。

### 验证

- **112 个 unittest 全部通过**（F1 +2, F3 +1, F6 +14, F2 +15, F7 +1 +1 -1 = +32）
- 行数：1122 → 1281（净增 +159；新常量 + helper，但 30 行重复 journal 逻辑抵消）
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

- [x] **F19** ✅ 已修复（6 轮 P0）— `warnings.pop(idx)` 推广到 `_check_required_subdirs`（按 index 精确 pop，支持多个 subdir 同时缺失场景）+ `_check_workspace_dir` 两处；新增 2 个 `--fix` 后 warning 清除测试
- [x] **F14** ✅ 已修复（6 轮 P0）— `set_status` 现在校验 `current_status in ALLOWED_TRANSITIONS[new_status]`；`done → in_progress` rollback 返回 False；`done → cancelled` 显式允许；新增 4 个转移校验测试（forward-only / done→cancelled / terminal 锁定 / 缺失 status 兼容）
- [ ] 检查新代码是否引入新的"分散赋值"或"重复逻辑"
- [ ] 检查新增 test 是否覆盖了失败路径（损坏、缺失、并发）
- [ ] 检查新命令是否在 `USAGE` 字典 + `USAGE.test_all_expected_command_keys_present` 都注册了
- [ ] 检查新增 helper 是否在所有 call site 都真的被用了（避免"声明了但没人调"的死代码）

---

## 2026-07-26 审查（第 6 轮 — 重构验证 + 新问题）

### 范围

- 被审查对象：`lite/.trellis-lite/scripts/trellis.py`（1316 行单文件，commit `21377146ed37` 之后）
- 审查维度：第 5 轮的 8 项修复是否真的生效；重构是否引入新问题；剩余 F5/F10/F11/F13 是否仍然成立
- 方法：3 个并行 subagent（验证 / 重构后回归 / 重评剩余项）+ 主线程综合

### 新发现（按优先级）

#### P0 止血（建议尽快修）

🔥 **F19**（曾名 F13，grew worse）：**doctor `--fix` 修复后 warning 仍残留在最终摘要里**
- 触发：F8 拆分时给 `_check_developer_file` + `_check_current_task` 的 `problems` 路径加了 `.pop()`，但**没把同模式推广到两个 `warnings` 路径**。
- 证据：`_check_required_subdirs` [trellis.py:1126-1131] + `_check_workspace_dir` [trellis.py:1153-1160] 修复完不清理 list。
- 用户体验：跑完 `--fix` 后看到 `⚠ N warning(s)` 列表里有刚被修复的项目，会怀疑"到底修没修好"。
- 修法：2 处 `warnings.pop()` + 2-3 个 `--fix` 测试，~30 行，预计 1h。
- 推荐：**本轮修复**（F8 拆出来之后这 bug 比之前明显；用户 daily-use 核心 UX；修法机械、风险 0）。

🔥 **F14**：**`ALLOWED_TRANSITIONS` 是死代码** —— 注释承诺"状态机"实际并不存在
- 触发：F6 把 `ALLOWED_TRANSITIONS` 加进 `set_status()` 但**实际只检查目标状态是否属于 `STATUSES`**（[trellis.py:265-266]），从未校验从当前状态到新状态的转移是否合法。
- 证据：`done → in_progress` 这种"rollback"调用会成功，违反 [trellis.py:56-57] 文档承诺的 "Forward-only transitions"。
- 影响：注释和测试都把 `ALLOWED_TRANSITIONS` 当成真实运行约束；任何维护者看到这个常量都会以为转移合法性受保护。
- 修法：在 `set_status()` 里加 `if current_status not in ALLOWED_TRANSITIONS[new_status]: return False`；同时 `ALLOWED_TRANSITIONS["done"]` 要包含 `cancelled`（cancel 应允许任何状态）。
- 推荐：**本轮修复**（F6 的承诺未兑现比没做更糟；测试已覆盖转移表，运行时一行代码即可生效）。

#### P1 收尾（F6/F9 没做完的部分）

🟠 **F15**：`cmd_session` line 862 用裸 `glob()` 绕过了 `list_journals()`
- 触发：F9 替换了 4 处 journal 枚举，但 `cmd_session` 末尾"统计所有 journal 的 session 总数"那段漏了。
- 证据：[trellis.py:860-863] `for j in sorted(workspace.glob(f"{JOURNAL_PREFIX}*.md"))`。
- 影响：`journal-draft.md` 等非编号文件会被计入"Total sessions"，但 `cmd_context` 的 `list_journals()` 不会。两个 command 对同一 workspace 的"journal 个数"可能不一致。
- 修法：替换为 `for num, j in list_journals(workspace)`。~3 行。

🟠 **F16**：`journal-1.md` 创建在 3 处重复
- 触发：`cmd_init` [L391-393] + `rotate_if_full` [L306-309] + `_check_workspace_dir` [L1156-1160] 都有 `# Journal 1\n\n` 字面字符串。
- 影响：header 文本/格式变更时三处必须同步修。F9 引入了 `rotate_if_full` 本应作为唯一定入口；后两处本应改为 `rotate_if_full(workspace, list_journals(workspace))`。
- 修法：让 `rotate_if_full` 始终创建文件（已是如此），把 `_check_workspace_dir` 和 `cmd_init` 改成调用 `rotate_if_full`。~10 行。

🟠 **F17**：`set_status` 在 `new_status not in STATUSES` 时抛 `ValueError`，所有调用方都不捕获
- 触发：F6 引入了 `raise ValueError(...)` 路径，但 `_task_start/_finish/_archive/_cancel` 都期望 helper 返回 `False` 走打印 Warning + 继续的降级路径。
- 影响：如果将来有人调用 `set_status(task, "paused")`（忘记在 `STATUSES` 加），会得到 stack trace 而不是友好的"请先 finish 这个任务"。
- 修法：把 `raise` 改为 `return False`，与 `set_status` 现有的"读取失败"路径统一。~3 行。

#### P2 一致性

🟡 **F18**：`set_status` 用裸 `json.loads` 而非 `read_json` —— 与仓库已有的 `read_json()` 模式重复
- 证据：[trellis.py:270-273] 手写 `try: json.loads(...) except (json.JSONDecodeError, OSError)`，而仓库已经在 [L180] 有 `read_json()`。
- 影响：两处对"missing/corrupted JSON"的处理模式不一致。
- 修法：让 `read_json` 加一个 `strict` 参数，或抽一个 `read_json_strict()` 给写操作专用。~5 行。

🟡 **F20**：`_check_journal_numbering` docstring 承诺"gap warning"但只查开头
- 证据：[trellis.py:1201-1209] docstring 写 "journal-N.md numbering should start at 1 (gaps are warnings)"，但代码只 `if nums[0] != 1`。
- 影响：当 `journal-1, journal-3, journal-5` 时中段间隔不会被警告。
- 修法：要么扩展到检测中段间隔（`if nums[i+1] != nums[i]+1: warn`），要么把 docstring 改成 "should start at 1"。

🟢 **F21**：`_check_workspace_dir` 重复 `get_developer()` + 返回 `_dev` 但 orchestrator 不用
- 证据：[trellis.py:1138-1139] `dev = get_developer()`（而 `get_workspace_dir()` 内部已经调过一次）；orchestrator 写 `workspace, _dev = _check_workspace_dir(...)` [L1072]。
- 修法：把签名简化为 `-> Path | None`，或先把 `dev` 算出来再调 `get_workspace_dir`（内部仍要重读 file IO，但签名更干净）。

#### P3 文档

📝 **F11 文档化**：`docs/design.md` 加一行区分 `created` vs `started`
- 触发：F11 被错怪为"代码 bug"，实际是文档没说清楚时间戳约定。
- 修法：在 design.md 的"任务系统"小节加：`created` = 任务记录创建时刻（planning 状态）；`started` = 第一次切到 in_progress 的时刻；任务可能从未被 start，所以 planning 任务上 `started` 不存在。
- 预计 5 分钟，0 风险。

### 验证

- **104 个 unittest 全部通过**（沿用第 5 轮）
- 行数：1122 → 1281（净增 +159）

### 第 6 轮审查方法论

第 5 轮是"做发现 → 列计划 → 实施"。第 6 轮是"**验证已交付 + 找重构暴露的新问题 + 重评剩余项**"——一种 retro 视角。

证据收集用了 3 个并行 subagent：
1. **verification-track**：8 项修复逐条 grep 证据，分 FOUND / DRIFTED / MISSING。结果：5 FOUND + 3 DRIFTED（F1 委托给 helper；F6 4 处而非 5 处 + ALLOWED_TRANSITIONS 是死代码；F9 还有 1 处裸 glob）。
2. **post-refactor-track**：在重构后的代码里找新问题（一致性、stale comments、helper 参数漂移、type-safety holes）。
3. **re-eval-track**：把第 5 轮"保留"清单的 F5/F10/F11/F13 用新上下文各做一次成本/收益重算。

**第 6 轮发现 vs 第 5 轮发现的关系**：
- F14/F15/F16/F17/F18/F20/F21 都是 F6/F8/F9/F2 重构**留下的一致性尾巴**——之前没有这些问题，因为没有 helper 要"被全部 call site 真正使用"。
- F19 是 F8 拆分时**漏掉的统一模式**——同一段代码（`--fix` 之后 pop 问题）只在一半 call site 上落地。
- 这印证了一个原则：**refactor 在解决老问题的同时，会暴露新的"未完成"债务**。第 5 轮的提交没把这些尾巴一起带走，是因为尾巴的形态只有重构之后才看得清。

### 第 6 轮建议的下一步

按上面的 P0/P1/P2/P3 顺序修复，预计净增 ~15-20 行代码 + ~50 行测试，总工时 2-3h。
完成后再做一次 commit `refactor(trellis-lite): execute 6th-round review tail (F14/F15/F16/F17/F19)`，把第 5 轮的承诺彻底兑现。

---

## 2026-07-26 修复（第 6 轮尾巴执行）

### 范围

- 被修复对象：`lite/.trellis-lite/scripts/trellis.py`（1316 行）+ `tests/test_status_machine.py` + `tests/test_doctor.py` + `tests/test_session.py` + `docs/design.md` + `CHANGELOG.md`
- 来源：上一节的 8 个新发现（F14/F15/F16/F17/F18/F19/F20/F21）+ F11 文档化
- 测试基线：104 → 112（净增 8）

### 已完成清单

| ID | 优先级 | 状态 | 改动摘要 |
|---|---|---|---|
| F19 | P0 | ✅ done | `_check_required_subdirs` 用 `idx = len(warnings)-1` 精确 pop（解决多 subdir 同时缺失场景）；`_check_workspace_dir` 两处 `warnings.pop()` 落地；新增 2 个回归测试 |
| F14 | P0 | ✅ done | `set_status` 增加 `if current in STATUSES and new not in ALLOWED_TRANSITIONS[current]: return False`；`ALLOWED_TRANSITIONS["done"]` 加入 `cancelled`；新增 4 个转移测试 |
| F17 | P1 | ✅ done | `set_status` 未知 status：`raise ValueError` → `return False`（统一所有失败模式） |
| F15 | P1 | ✅ done | `cmd_session` 行 887 裸 `glob()` → `list_journals(workspace)`；新增"非编号 journal 文件不计入 total"测试 |
| F16 | P1 | ✅ done | `cmd_init` + `_check_workspace_dir` 改调 `rotate_if_full(workspace, list_journals(workspace))`；3 处 `# Journal 1\n\n` 字面字符串收敛到 1 处 |
| F18 | P2 | ✅ done | 新增 `read_json_strict(path) -> dict \| None` helper（区分 missing/corrupted/empty），`set_status` 改用它；`read_json` 加 docstring 注明"prefer read_json_strict for writes" |
| F20 | P2 | ✅ done | `_check_journal_numbering` 增加 `for i in range(len(nums)-1): if nums[i+1] != nums[i]+1: warn`；新增"journal 内部间隔"测试 |
| F21 | P2 | ✅ done | `_check_workspace_dir` 签名 `(fix, warnings) -> Path \| None`（不再返回 `_dev`）；orchestrator 同步简化 |
| F11 | P3 | ✅ done | `docs/design.md` 任务系统小节加"时间戳约定"段（`created` vs `started` vs `finished`/`archived`/`cancelled`） |

### 测试覆盖增量

- `tests/test_status_machine.py`：+4 测试（forward-only / done→cancelled / terminal block / 缺失 status 兼容）
- `tests/test_doctor.py`：+3 测试（`--fix` 后 subdir warning 清除 / `journal-1.md` 自动创建后无 warning / 内部间隔警告）
- `tests/test_session.py`：+1 测试（`journal-draft.md` 不计入 Total sessions）

总计：104 → **112**（+8），全部通过。

### 验证

- **112 个 unittest 全部通过**（14.0s）
- 行数：1281 → 1316（净增 +35，含代码 + 测试 + 注释）
- CHANGELOG.md 在 `[Unreleased]` 增加 5 条修复说明 + 1 条文档说明（全部面向用户可观测行为）

---

## 历史审查

- 2026-07-26 — 第 6 轮（重构验证 + 新问题，commit `21377146ed37` 之后）
- 2026-07-26 — 第 5 轮（commit `21377146ed37`，F1/F3/F4/F6/F8/F9/F2/F7）
- 2026-07-12 — 第 4 轮（见 git log `feat: fourth-round UX enhancements`）
- 2026-07-08 — 第 3 轮（流程审查，commit 4154cb089519）
- 2026-06-30 — 第 2 轮（质量审查，PR/issue 计数待补）
- 2026-06-15 — 第 1 轮（首版审查，commit f94d2d1）
