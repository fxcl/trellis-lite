# Trellis Lite 变更日志

> 配套文档：[README](../README.md) · [usage-guide](usage-guide.md) · [design](design.md) · [exit-codes](exit-codes.md)

本文档记录 Trellis Lite 面向用户的**可观测变更**（新功能、行为变更、修复、破坏性变化）。
源码重构、测试工具调整等不影响最终用户的修改不在此列出。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

---

## [Unreleased] - 2026-08-07

### 新增
- **四平台 agents / commands / skills 全量补齐（platform parity）**：Qoder、Claude Code、OpenCode、Cline 现在获得一致的 Trellis 能力分发，py 仍是唯一逻辑源、`.trellis-lite/skills/` 仍是唯一正文源 ——
  - **Qoder**：`.qoder/agents/` 现装 3 个专用 agent（新增 `trellis-implement`，补齐 brainstorm / implement / check 三件套）；新增 `.qoder/skills/` 分发，共 12 个 slash 入口——首次安装时生成：4 个深度流程 skill（brainstorm / before-dev / check / update-spec，源 `.trellis-lite/skills/*.md`）+ 8 个 py 命令映射（trellis-context / trellis-new / trellis-start / trellis-finish / trellis-archive / trellis-doctor / trellis-cancel / trellis-list，源 `templates/claude/commands/`，与 Claude/OpenCode 同源；`/trellis-check` 由深度流程版承担），四平台 slash 入口对等；重装不覆盖，源更新后删 `.qoder/skills/trellis-*/` 重装可重新生成
  - **Claude Code**：新增 `.claude/commands/` 9 个 `/trellis-*` 命令（trellis-context … trellis-list，扁平 `trellis-*.md` 文件名，三平台统一命名空间）
  - **OpenCode**：`.opencode/agents/` 同步补齐 `trellis-implement`；新增 `.opencode/commands/` 9 个同名命令（与 Claude 版同源，仅去 `allowed-tools` frontmatter 行）
  - **Cline**：新增 `.cline/skills/` 分发，共 12 个 slash 入口，与 Qoder 由同一生成循环产出（字节级一致）——4 个深度流程 skill（源 `.trellis-lite/skills/*.md`）+ 8 个 py 命令映射（源 `templates/claude/commands/`）；经 `/skill-name` 或 description 自动匹配触发；Cline 无独立 agents 机制（单会话，主会话直接实现）；重装不覆盖，源更新后删 `.cline/skills/trellis-*/` 重装可重新生成
  - **uninstall.sh 同步**：卸载时只清理 Trellis 命名空间（`.qoder/` 的 trellis-* agents+skills、`.cline/skills/` 的 trellis-*、`.opencode/` 的 trellis-* agents+commands、`.claude/commands/` 的 trellis-* 命令），用户自建的同目录文件不受影响，空父目录一并移除
  - 文档同步：AGENTS.md / CLAUDE.md / platforms.md / usage-guide.md 改为与实际安装产物一致的事实表述；测试套件增至 204 个（test_install.py 新增三平台部署与卸载清理、模板不变量〔claude↔opencode 命令同源、frontmatter 合法 YAML〕、卸载保留用户自建平台文件覆盖，含 qoder/cline SKILL.md verbatim 正文与双平台字节一致断言）

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
- **`session --commit` 现在接受 4–64 位 hex SHA**：之前正则锚定 4–40 位 hex，仅支持 SHA-1。Git 2.42+ 引入 SHA-256 作为默认哈希算法后，commit 字段被误判为“格式错误”拒绝写入。新行为：regex 改为 `^[0-9a-f]{4,64}$`，同时支持 SHA-1 (40) 和 SHA-256 (64)；错误提示同步更新。
- **`task start` 的 in-progress 冲突警告改为汇总单条**：之前 N 个其他 in_progress 任务输出 N 行 `Warning: '...' is still in_progress`；新行为：扫一遍 tasks/ 收集冲突列表，输出**单条**汇总 warning（含计数 + 全部冲突任务名 + 清理建议），减少视觉噪音同时保留全部信息。
- **`resolve_task_dir` 现在用异常信号歧义与缺失**：之前把两种错误都塞进 `return None` + 各自打印，调用方需要再手打一次 `Task not found: ...`（导致重复消息）。新行为：拆为 `AmbiguousTaskName(Exception)`（携带候选列表）和 `FileNotFoundError`，新增 `resolve_or_report()` 包装函数集中翻译为用户消息；`_task_start` / `_task_archive` / `_task_cancel` / `_task_delete` 4 个调用方都改用包装函数，删除冗余的 `Task not found` 行。
- **`cmd_doctor` 删去死代码 try/except**：原本早退分支的 `try/except Exception` 是为了让 `_check_trellis_present` 的 "missing" 信息统一走 problems 列表，但实际上下游检查已经处理该路径。新行为：直接调用 `get_repo_root(init_ok=True)`，依赖 `_check_trellis_present` 统一报告，少 4 行嵌套结构。
- **`_task_delete` 状态判断改用直接比较**：之前 `if status not in ("cancelled",)`（一个元素的元组，可读性差 + 容易被误改成 `(cancelled, archived)`）；新行为：`if status != "cancelled"`，与设计意图一致。

### 修复（第 5 轮 oracle-reviewer）
- **`task start` 现在显式拒绝重启已终态任务（done / archived / cancelled）**：之前 forward-only 状态机（`ALLOWED_TRANSITIONS`）会拒绝 `done → in_progress`，但 `_task_start` 只看到 `set_status` 返回 `False` 就报 "missing or corrupted" 警告 + 打印 "✓ Task started" + 切换 `.current-task`，造成 split-brain（状态未变但指针已切）。新行为：在调用 `set_status` 之前预检当前状态；如果命中 `done / archived / cancelled`，明确报错 `Error: cannot start a task in terminal state '...'` + exit 1，不切换 `.current-task`，消除误导消息与状态/指针不一致。
- **文档与实现对齐**：4 处文档行数 `~1330` 修正为 `~1370`（README.md / best-practices.md / design.md 三处）；测试数量 `123` 修正为 `125`（best-practices.md / design.md）；`workflow-checklist.md` commit hash 描述从 `4-40 位 hex` 同步为 `4-64 位 hex`（与 F19 一致）；`design.md §5` 运行测试命令从 `unittest discover -s lite/tests -t .` / `lite.tests.test_task`（在 Python 3.9+ 会因相对 import 失败）改为 `tests.test_*` 列表写法。

### 文档（第 5 轮 oracle-reviewer）
- `best-practices.md` 修正第 16 节“决策清单”中“CLI 已会拒绝多 in_progress”的描述：实际 CLI 只 Warning + 返 0，由人工自律。`--replace` 描述同步修正（显式接管，不是替换同名任务）。
- README.md / usage-guide.md / design.md / best-practices.md 同步：测试数量 112 → 123；行数 906 → 1100+；子命令清单加 `task delete` / `version` / `doctor` / `task list --all`。
- 运行测试命令修正：之前 `python3 -m unittest discover -s lite/tests -t .` 在 Python 3.9+ 相对 import 失败；改为 `python3 -m unittest tests.test_*`。
- AGENTS.md 命令清单补全 `task delete` / `doctor` / `version`。
- `exit-codes.md` 新增"退出码不对称 rationale"章节：解释 `task finish` 在 `task.json` 损坏时返回 1（不可逆，须中止）vs `start` / `archive` / `cancel` 返回 0（可恢复，降级继续）的设计依据。
- `docs/design.md` 任务系统小节补"时间戳约定"：明确 `created` / `started` / `finished` / `archived` / `cancelled` 各自对应哪个事件；解释 `planning` 任务**没有** `started` 字段是正确语义。
- `install.sh` --help / 输出现范补"重装语义"：说明重装不会覆盖已有 `.developer`、AGENTS.md、CLAUDE.md、.clinerules/、.gitignore runtime 条目、pre-commit hook，仅在目标未安装时执行初始化动作。

### 修复（第 6 轮 oracle-reviewer）
- **`task archive` 现在显式拒绝归档已取消任务**：之前 forward-only 状态机（`ALLOWED_TRANSITIONS`）会拒绝 `cancelled → archived`（cancelled 是 terminal），但 `_task_archive` 只看到 `set_status` 返回 `False` 就报 "missing or corrupted" 警告 + 仍然执行 `shutil.move`，产生 split-brain（目录在 `archive/2026-MM/` 但 `task.json` 仍 `status=cancelled`，`task list --all` 显示 `[cancelled]`）。新行为：在调用 `set_status` 之前用 `read_json_strict` 预检；如果命中 `cancelled`，明确报错 `Refusing to archive: '...' is cancelled.` + exit 1，**不移动目录**（与 F27 `_task_start` 的拒绝模式对称）。
- **`session` 不再 traceback（workspace 损坏保护）**：之前 `rotate_if_full` 在 `workspace/<dev>/` 是文件时（误触、git 误同步、中途崩溃残留）直接 `journal.write_text()` 到文件路径，抛 `NotADirectoryError` 未捕获，用户看到 raw Python 堆栈。新行为：`rotate_if_full` 头部加 `if workspace.exists() and not workspace.is_dir(): raise NotADirectoryError(...)`，`cmd_session` 顶层 `try/except NotADirectoryError → print colored Error + return 1`。消息明确指向 `trellis.py doctor --fix`。
- **`session` 区分 .developer 损坏 vs 未初始化**：之前 `.developer` 文件存在但无 `name=` 行（被 git 误同步、编辑器崩溃）时，`get_developer()` 返回 None，`session` 错误消息说“Run: trellis.py init <name>”，误导用户重新 init（覆写可恢复文件）。新行为：检测到 `.developer` 文件存在时给独立错误消息，推荐 `doctor --fix` 或 init（明说 init 会覆写）。
- **`task delete` 拒绝路径补充 .current-task tip**：之前 `task delete` 拒绝 in_progress 任务后 `.current-task` 仍指向该任务（拒绝路径不清理指针是合理的），但用户可能错过这个状态。新行为：拒绝路径里若 `.current-task` 还指向被拒任务，补充 `Tip: 'task current' still shows this task; run 'task cancel' first ...` 提示；非活跃任务不打印这个 tip。

### 文档（第 6 轮 oracle-reviewer）
- 测试数量 `123` 同步为 `125`（README.md / design.md L210 / usage-guide.md L313+L347；第 5 轮漏修了 design.md "本轮（质量提升）"行 + README.md / usage-guide.md）。

### 测试
- `TestUninstall` 5 个新测试覆盖 `uninstall.sh` 的 `.gitignore` 清理与 pre-commit hook 移除路径（含 O9 补充覆盖 + O11 回归保护：用户在 `.gitignore` 标记块内插入注释/空行后，uninstall 仍能完全清理所有 `.trellis-lite/.X` 条目）。
- `TestUninstall` + `TestInstall` 新增 3 个 O14/O16 测试：`test_uninstall_ignores_non_marker_mentions`（散文 marker 不误触发清理）、`test_install_preserves_existing_developer_on_reinstall`（重装保留 dev name）；`TestUninstall.setUp` O17 增强：git init 失败时 `self.skipTest()` 避免 false-positive。测试总数 116 → 123。

---

### 修复（第 7 轮 oracle-reviewer）

**核心模式：所有 mutating commands（`task start` / `task archive` / `task cancel`）现在用 `read_json_strict` 预检 task.json 状态，对 missing/corrupted 元数据显式拒绝。F46-F52 修复了第 6 轮修复遗漏的姊妹 case 与 broken promise。**

- **`doctor --fix` 在 `workspace/<dev>` 是 regular file 时不再 traceback（F46）**：之前 `mkdir(parents=True, exist_ok=True)` 在文件路径上抛 `FileExistsError`（Python 3.12+），raw traceback 让 `cmd_session` 的 "Run 'trellis.py doctor --fix' to repair" 推荐路径自身崩溃。**这是 F44 修复的 broken promise**。新行为：新增 `_safe_mkdir()` helper 检测并 unlink 同路径的 stray file，再 mkdir；推广到 `_check_required_subdirs`（3 个子目录）+ `_check_workspace_dir`，共 4 处修复。新增 2 个 doctor 测试覆盖 workspace 和 spec/ 两种 stray-file 场景。
- **`task start` 在 `task.json` 损坏时拒绝切换 `.current-task`（F48）**：F27 修了 `done/archived/cancelled` 已知 status，但 corrupted task.json 时 `read_json` 返 `{}`，fall through 到 `set_status` 失败后**仍**执行 `set_current_task` + 打印 "✓ Task started"，造成 split-brain（指针指向元数据不可读的任务）。新行为：用 `read_json_strict` 预检，missing/corrupted 时报 `Error: '.../task.json' is missing or corrupted; refusing to start.` + exit 1，不切换 `.current-task`。新增 1 个 test 覆盖。
- **`task archive` 在 `task.json` 损坏时拒绝归档（F47）**：F32 修了 `cancelled` 状态，但 corrupted task.json 时仍打 warning + 执行 `shutil.move` 到 `archive/`，产生 orphan archived task（`task list --all` 显示 `[?]`）。新行为：`read_json_strict` 预检，missing/corrupted 时报 `Refusing to archive: '.../task.json' is missing or corrupted.` + exit 1，目录不移动。fallback 分支同步改为 hard-error（避免 set_status mid-operation 失败时的 silent split-brain）。新增 1 个 test 覆盖。
- **`task cancel` 现在显式拒绝取消已 archived 任务（F52）**：之前 `archived → cancelled` 违反 ALLOWED_TRANSITIONS（archived 是 terminal），但 `_task_cancel` 只看到 `set_status` 返回 `False` 就报**误导性** "missing or corrupted" warning + 清除 `.current-task` + 打印 "✓ Task cancelled"，task.json 仍 archived。新行为：`read_json_strict` 预检，archived 时报 `Refusing to cancel: '...' is archived. Archived is a terminal state...` + exit 1，指针不清理；已 cancelled 任务改为 idempotent note（不再打误导 warning）；corrupted task.json 同样拒绝。fallback 分支同步改为 hard-error。新增 2 个 test 覆盖 archived + corrupted。
- **`install.sh` 部分安装失败时自动 rollback（F50）**：之前 `set -e` 在 init 失败（Python 缺失 / 权限拒绝 / Python 3 < 3.9）时立即退出，但 `.trellis-lite/` + `AGENTS.md` + `CLAUDE.md` + `.clinerules/trellis-lite.md` 已写入 target，**无 cleanup**。重跑 install.sh 时 `if [ -d "$DST_TRELLIS" ]` 检测到 partial state 静默跳过 cp，用户卡在 broken state 需手动 `rm -rf`。新行为：跟踪 `INSTALLED_FILES` 数组，setup `trap rollback ERR`，init 失败时自动清理所有已安装文件；init 成功（即使后续 gitignore / hook 步骤失败）则 `trap - ERR` 关闭 rollback（不清理已成功部分，给用户手动修复机会）。

### 文档（第 7 轮 oracle-reviewer）

- `architecture-review.md` 第 7 轮新增：F46-F52 修复记录；F50 install.sh rollback 设计 rationale。

### 测试
- `tests/test_doctor.py` 新增 2 个测试（`test_doctor_fix_recovers_from_file_workspace` + `test_doctor_fix_recovers_from_file_subdir`）覆盖 `_safe_mkdir` 路径。
- `tests/test_task.py` 新增 4 个测试（`test_start_rejects_corrupted_task_json` / `test_archive_rejects_corrupted_task_json` / `test_cancel_rejects_archived_terminal_state` / `test_cancel_rejects_corrupted_task_json`）覆盖 F47/F48/F52。
- 手工烟测覆盖 4 个 P1 修复 + install.sh rollback 路径（happy path + Python 失败 path）。
- 测试总数 131 → **137**（+6），全部通过；loc 1442 → 1543（+101，含 helper + 注释 + 测试）。

### 修复（第 8 轮 oracle-reviewer）

第 8 轮审查深度确认 F46/F47/F48/F50/F52 五项修复全部生效且无新缺陷。**本轮 0 个 P1 代码缺陷**，3 个 P2 与 1 个 P3 均为 docs/correctness 同步问题，加上 1 个 P3 代码对称化（F53 `task delete` corrupted 预检，补齐 4 个 mutating commands 的对称契约）。

- **`task delete` 在 `task.json` 损坏时拒绝（F53）**：F47/F48/F52 修复了 `start` / `archive` / `cancel` 在 corrupted 时的对称拒绝路径，但 `_task_delete` 仍用 `read_json`（lossy），corrupted 时 `data.get("status", "?")` 静默回到 `"?"`，打印**误导性** hint `"Cancel it first (task cancel X)"` — 但 `task cancel` 自身在 corrupted 时也直接拒绝（F52），把用户困在"先 cancel，但 cancel 又拒绝"的循环里。**F53 是 F47/F48/F52 系列的姊妹补丁**：用 `read_json_strict` 预检，corrupted 时报 `Refusing to delete: '.../task.json' is missing or corrupted. Run 'trellis.py doctor --fix' to repair, or 'task delete --force <name>' to discard.` + exit 1，**目录不删**（`shutil.rmtree` 在 corrupted 情况下是不可逆的，删除前必须保住失败路径）。`--force` 旁路保留，可作"最后手段"。新增 1 个测试覆盖。
- **`test_archive_done_task_succeeds` 时间炸弹修复**：原测试 hardcoded `08-05-t`（trellis.py 用 `datetime.now().strftime("%m-%d")` 生成 `MM-DD-<slug>` 命名），跨日（8-05→8-06）后必失败。改为用 `datetime.now()` 动态生成 `today_prefix`，跨日期无 flakiness。

### 文档（第 8 轮 oracle-reviewer）

第 7 轮修复改变了 `task start` / `archive` / `cancel` 的实际行为（从 "corrupted 时返 0 + Warning" 改为 "返 1 拒绝"），但 `best-practices.md § 7` + `exit-codes.md` 的设计依据仍描述"非对称设计"。第 8 轮统一这两份文档的契约描述：

- **`best-practices.md § 7.1` 退出码表格**：start/archive/cancel 行从"Warning + 返 0"改为"拒绝 + 返 1"，补"split-brain 风险"原理列；新增"统一原则"段：所有会修改活跃指针或目录位置的 mutating task 命令，corrupted `task.json` 一律返 1。
- **`best-practices.md` 坑 6**：修法段从"start/archive/cancel 返 0 + Warning"改为"也返 1（自第 6-7 轮 oracle-reviewer 后）"。
- **`best-practices.md` 决策清单 DO 行**：可逆/不可逆二分法改为"mutating task 操作依赖返 1 + split-brain 防护"。
- **`exit-codes.md` 设计依据段 § "为什么 task finish 返 1 而 start/archive/cancel 返 0"**：整段重写为对称严格模式 + split-brain 依据 + 恢复路径（doctor / 手动 / --force 删除）+ 与查询类命令的区分 + 历史注（0.6.7 之前的非对称设计）。
- **`design.md` § 5 CI 步骤 4**：`125 个` → `137 个`（F57）。
- **`usage-guide.md` 自带测试套件**：测试文件级表格重写——`test_task.py` 19 → 38 / `test_session.py` 7 → 9 / `test_install.py` 4 → 15；新增 5 行覆盖之前完全未列出的测试模块（`test_doctor.py` 13 / `test_precommit.py` 4 / `test_slugify_fuzz.py` 6 / `test_status_machine.py` 20 / `test_usage_consistency.py` 15）；总表 40 → **137**（F58）。F59 同步测试运行命令补 `tests.test_status_machine tests.test_usage_consistency`（与 `design.md` 对齐）。

### 测试（第 8 轮 oracle-reviewer）

- `tests/test_task.py` 新增 `test_delete_rejects_corrupted_task_json`（F53 对称化 + 误导 hint 移除 + 目录存活断言）。
- `tests/test_task.py` 修复 `test_archive_done_task_succeeds` 日期时间炸弹（hardcoded `08-05` → dynamic `today_prefix`）。
- 138 个 unittest 全部通过（25.114s）。

### 修复（第 9 轮 oracle-reviewer）

第 9 轮审查确认 0 个 P1；2 个 P2 均已修复。本节同时补记第 8 轮后未入 CHANGELOG 的 F54 / F55 / F62 变更。

- **`task create --replace` 自动关闭旧任务（F49）**：之前 `--replace` 只切换活跃指针，旧任务停留在 `in_progress` 成为隐形孤儿（下次 `task start` 会报冲突 warning）。新行为：接管时自动将旧任务置为 `done`（含 `finished` 时间戳）；旧目录缺失/已终态/corrupted 时安全跳过，无部分状态风险。
- **`task delete --force` 绕过 corrupted 守卫（F63）**：F53 的非 force 拒绝消息推荐 `task delete --force <name>` 作为恢复路径，若 `--force` 也拒绝 corrupted 则用户被困在死循环。新行为：`--force` 跳过 corrupted 预检直接删除（含清理 `.current-task` 指针），作为“最后手段”真正可用。
- **`task current` / `task context` 感知 corrupted 活跃任务**：之前用 lossy `read_json`，corrupted 时静默输出 `Title: ?` 假装健康。新行为：`read_json_strict` 检测后输出 warning（指向 `doctor --fix`）+ exit 0（查询类命令不阻断）。
- **`doctor --fix` 从 workspace 恢复 developer 名**：之前 `.developer` 缺失时无条件写 `name=developer`，孤立真实 workspace/<真名>/ 导致 journal 不可达。新行为：workspace/ 恰好 1 个子目录时恢复真名，0/2+ 时才回落默认。
- **`doctor` 报告 corrupted 活跃任务为 Problem（F55）**：`.current-task` 指向的 `task.json` 损坏时不再显示绿色 `✓ Active task (?)`，改为 `✗` + Problem（驱动 exit 1，pre-commit hook 阻断 commit）；`--fix` 不自动清该指针（用户需自行决定手动修复还是 `task delete --force`）。
- **`doctor` 完整性检查递归 archive（F54）**：之前只扫 `tasks/*/`，已归档任务的孤儿目录/corrupted `task.json` 完全不可见。新行为：递归扫 `tasks/archive/<月>/*/`，报告带 `archive/<月>/` 前缀。
- **`doctor --fix` 修复 `.developer` 无 name= 行（第 9 轮 P2-1）**：`session` 在该状态推荐 `doctor --fix`，但之前 `--fix` 只覆盖“文件缺失”分支，推荐路径是死路。新行为：两种损坏形态均用同一恢复逻辑修复（单 workspace 子目录恢复真名，否则默认 developer）。
- **`install.sh` / `uninstall.sh` 要求 bash 4+（F62）**：脚本使用 `read -ra` 与 `arr+=()` 语法，macOS 自带 bash 3.2.57 会静默错误。新行为：`install.sh` 头部显式检查版本，不满足时报错退出并提示 `brew install bash`；README 同步前置要求。

### 文档（第 9 轮 oracle-reviewer）

- **`best-practices.md § 8` 与实现对齐（P2-2）**：§8.1 检查 #2/#5/#6 补两种损坏形态、F55 corrupted Problem、F54 archive 递归描述；§8.2 从“不能修复 problems”改为“能修 2 类 Problem”（`.developer` 缺失、stale `.current-task`），并补 developer 真名恢复语义。
- **数字同步**：行数 `~1543`/`~1370` → `~1704`，测试数 `137` → `151`（README / design / usage-guide / best-practices 四处）；usage-guide 测试表格按模块刷新（task 38→43 / context 10→11 / doctor 13→21）。

### 测试（第 9 轮 oracle-reviewer）

- `tests/test_doctor.py` 新增 P2-1 双测试（no-name 分支恢复真名 + 多 workspace 回落默认）；早前补 F54/F55 共 4 个、developer 恢复 2 个。
- `tests/test_task.py` 新增 F53 corrupted 拒绝 + F63 `--force` 绕过测试；修复 `test_archive_done_task_succeeds` 日期时间炸弹。
- `tests/test_install.py` 新增 `_has_bash_4plus()` 探测，macOS bash 3.2 下 install/uninstall 类测试 `skipTest`（CI Linux bash 5+ 正常跑）。
- 151 个 unittest 全部通过（macOS 上 skipped=15 为 bash 版本 skip，非失败）。

### 改进（第 9 轮 P3 跟进）

- **`task finish` 分层报错（P3-4）**：之前 `set_status` 返回 `False` 一律报 "missing or corrupted"，但终态任务（`.current-task` 被手改指向 cancelled/archived 任务）也会命中同一路径，把用户导向 doctor 修不了的问题。新行为：与 `task start` 对称的分层预检 —— corrupted 指向 `doctor --fix`；终态报 `terminal state '<s>'` + 提示检查指针；中途写失败单独报错。所有拒绝路径均不清活跃指针。
- **`doctor --fix` developer 回落时警告 orphan workspace（P3-5c）**：之前回落到 `developer`（或任何不覆盖全部子目录的名字）时，其余 workspace 子目录的 journal 静默不可达。新行为：输出一条 warning 列出不可达目录 + 提示 `init <name>` 切换身份。
- **`help` 展示 `--replace` / `--force` 标志（P3-6）**：`task create` / `task delete` 行补参数及一行说明，提高可发现性。

### 测试（第 9 轮 P3 跟进）

- `--replace` 三边界测试（P3-5a）：旧任务目录缺失（stale 指针）/ 已终态（cancelled 不被触碰）/ corrupted（原文件保留待 doctor），均断言 create 成功 + 无部分状态。
- `--force` 删除两处补 `.current-task` 清理断言（P3-5b，防未来 refactor 静默丢指针清理）。
- finish 终态分层报错测试（P3-4）+ orphan workspace 警告测试（P3-5c）。
- 测试总数 151 → **156**，全部通过；trellis.py 1704 → 1756 行；数字同步 README / design / usage-guide / best-practices（P3-3 同时修正 §7.1 标题与示例的“非对称”残留表述、exit-codes.md 的 `pre-task.json` 笔误）。

### 改进（第 10 轮 oracle-reviewer）

第 10 轮审查 0 P1 / 0 P2，8 项 P3 全部处理；审查宣告收敛（后续改为事件驱动：新功能时再审）。

- **doctor 报告终态指针（P3-A）**：`.current-task` 指向 cancelled/archived 任务时不再显示绿色 `✓`，改为 Warning ⚠ + 恢复选项（`--replace` / `task start <other>` / 手删指针），闭合 `task finish` 拒绝消息的指引链；`task cancel` 幂等分支同时补清指向自身的指针（之前早退在清指针代码之前，用户被困在只能手改指针的状态）。
- **orphan 警告护栏（P3-B）**：新增负向测试（非 `--fix` 模式不泄漏 orphan 警告）；正测试加强为断言 summary 条目含逗号拼接的目录列表。
- **doctor 检查项 pop 健壮化（P3-C）**：`_check_developer_file` 两处 `pop()` 改为 idx 定位（与 `_check_required_subdirs` 同模式），未来检查项重排/新增不会 pop 错条目。
- **orphan 文案修正（P3-D）**：多目录时每个目录对称渲染 `workspace/<x>/`（之前只有末项带尾斜杠），并补“选哪个名字”提示。
- **help 列对齐统一（P3-E）**：所有命令行改经 `_help_line` 渲染，描述列固定 36（之前漂移 31–39）；新增 ANSI 剥离后的列对齐护栏测试；help 命令枚举测试补齐 task current / task list / task delete / doctor / help / version。
- **finish 措辞对称（P3-F）**：中途写失败消息补 "Check file permissions and try again."（与 start/cancel/archive 对齐）；对已 done 任务的幂等 finish 输出 Note（崩溃窗口恢复路径，不再看似新完成）。
- **文档修正（P3-G）**：best-practices §6.3 删除“doctor 会报 Warning”的虚假承诺（doctor 无时间戳合法性检查），降级为人工判断；§6.4 `--replace` 示例补自动关闭旧任务语义（第 9 轮 P3-2 遗留）；§8.1 检查 #5 补终态指针描述。

### 测试（第 10 轮 oracle-reviewer）

- 新增 5 个测试：doctor 终态指针 warning（P3-A）、orphan 负向护栏（P3-B）、help 列对齐（P3-E）、finish archived 终态分支（P3-H）、cancel 幂等清指针（P3-A）。
- 测试总数 156 → **161**，全部通过；trellis.py 1756 → 1814 行；数字同步 README / design / usage-guide / best-practices。

### 改进（第 11 轮 oracle-reviewer）

第 11 轮审查 0 P1 / 0 P2，8 项 P3 全部评估为可选优化；处理 4 项低（实际代码加固 + 文档同步），跳过 4 项极低（设计选择 / 边缘 race）。审查保持事件驱动。

- **`task archive` 兼容 stray file 路径（P3-3）**：`_task_archive` 的 `tasks/archive/` 目录创建改为 `_safe_mkdir`（与 doctor --fix 同模式）。Python 3.12+ 会在路径被文件占用时抛 `FileExistsError` 暴露 traceback，新行为：透明移除 stray 文件并重建目录。
- **`session` 兼容 workspace 完全缺失（P3-4）**：`rotate_if_full` 防御闭最后一道缺失场景—— `workspace/<dev>/` 整体不存在时 `write_text` 抛 `FileNotFoundError` 的 traceback。新行为：在 `NotADirectoryError` 检查后增加 `if not workspace.exists(): workspace.mkdir(parents=True, exist_ok=True)`，与 `cmd_init` / `_check_workspace_dir` 路径一致。
- **顶层 `AGENTS.md` 命令清单补齐（P3-2）**：仓库根 `AGENTS.md` L84 缺 `task delete` / `doctor` / `version`，已补全为 `init, task create/start/current/finish/archive/cancel/list/delete, session, context, specs, doctor, version`。
- **文档行数同步（P3-1）**：实际 1824 行已同步到 README / design.md / best-practices.md。

### 测试（第 11 轮 oracle-reviewer）

- `tests/test_task.py` 新增 `test_archive_recovers_from_file_archive_dir`（P3-3 锁回归）。
- `tests/test_session.py` 新增 `test_session_workspace_missing_does_not_traceback`（P3-4 锁回归）。
- 测试总数 161 → **163**，全部通过；trellis.py 1814 → 1824 行；数字同步 README / design / usage-guide / best-practices。

### 改进（第 12 轮 oracle-reviewer）

第 12 轮审查 0 P1 / 0 P2，5 项 P3 全部评估为可选优化；处理 4 项低（实际代码加固 + 文档同步 + 死代码清理），跳过 1 项流程元（[Unreleased] 区块待 release 前 review）。审查保持事件驱动。

- **删除 `FILE_CONFIG` 死代码（P3-1）**：常量全文 0 引用、无任何 `config.yaml` 访问点，删除避免误以为真实配置文件引入技术债。
- **`_safe_mkdir` 防御网扩展到祖先路径（P3-2）**：之前只防御 `p` 本身是文件；现在上朔到 `p.parent` 链，任何祖先是文件也会被 unlink，修复了 `.trellis-lite/tasks` 是 stray file 时 `mkdir(tasks/archive)` 报 `NotADirectoryError` 的 traceback 边角。`cmd_init` 的 3 处 mkdir 同步升级为 `_safe_mkdir`。
- **文档行数同步（P3-3）**：实际 1842 行已同步到 README / design.md / best-practices.md。
- **测试数 163 同步（P3-4）**：README L131 / design.md L210 + L233 漏改 161 → 163，现已补齐。

### 测试（第 12 轮 oracle-reviewer）

- `tests/test_init.py` 新增 `test_recovers_from_file_in_init_path`（P3-2 锁回归）。
- 测试总数 163 → **164**，全部通过；trellis.py 1824 → 1842 行；数字同步 README / design / usage-guide / best-practices。

### 改进（第 13 轮 oracle-reviewer）

第 13 轮审查 0 P1 / 0 P2 / 3 项 P3；本轮处理全 5 项（2 项 P2 文档同步 + 3 项 P3 优化）。连续 4 轮（10/11/12/13）0 P1，代码核心契约在跨调用者追踪中全部成立，无回归，进入维护收敛态。

- **README 测试命令补全（P2-1）**：README L135-137 的测试命令遗漏了 `tests.test_status_machine` 和 `tests.test_usage_consistency` 两个模块（按文档操作会少跑 21% 测试），现已补齐与 design.md / usage-guide.md 一致；同时 L131 测试数 163 → 164。
- **design.md 测试数同步（P2-2）**：L210 + L233 测试数 163 → 164（与 README / usage-guide / best-practices 对齐）。
- **`_task_archive` 归档原子化（P3-1）**：之前首次月份归档时 `shutil.move` 因 `dest.parent`（月份目录）不存在而回退到 `copytree + rmtree` 非原子路径（崩溃窗口内任务可能同时存在于 `tasks/` 和 `archive/`）；现在 `_safe_mkdir(dest.parent)` 预建月份目录，`shutil.move` 始终走 `os.rename` 原子路径。祖先 walk 同时创建 archive 容器，原 `_safe_mkdir(archive_dir)` 被吸收。
- **`_check_workspace_dir` pop 模式统一（P3-2）**：两处裸 `warnings.pop()` 改为 `idx = len(warnings) - 1` + `warnings.pop(idx)`，与 `_check_developer_file` / `_check_required_subdirs` 一致，防止未来插入新检查项时 pop 移除错误条目。
- **`_safe_mkdir` docstring 精度（P3-3）**：措辞从 "non-`.trellis-lite` paths are never touched" 改为 "all callers operate under `.trellis-lite/`"，避免函数自身不具备的边界保证误导未来调用方。

### 测试（第 13 轮 oracle-reviewer）

- `tests/test_task.py` 新增 `test_archive_precreates_month_dir_for_atomic_move`（P3-1 锁回归）：in-process 拦截 `shutil.move`，断言 `dest.parent`（月份目录）在 move 调用前已存在，保证走原子 rename 路径。
- 测试总数 164 → **165**，全部通过；trellis.py 1842 → 1857 行；数字同步 README / design / usage-guide / best-practices。

### 改进（第 14 轮 oracle-reviewer）

第 14 轮审查 0 P1 / 0 P2 / 3 项 P3，全部为文档/注释层面，全 3 项处理。连续 5 轮（10/11/12/13/14）0 P1，连续 3 轮（12/13/14）0 P2，代码核心契约跨调用者追踪全部成立，确认进入维护收敛态。

- **CHANGELOG 链接日期修正（P3-1）**：`[Unreleased]` 错误引用了 0.6.9 的发布日期（2026-07-26），实际标题日期为 2026-08-07；GitHub markdown 锚点无法匹配。
- **对称拒绝 rationale 补全 `task delete`（P3-2）**：exit-codes.md §37 标题和正文从“四个命令”改为“五个命令”（含 `delete`），补 `delete` 副作用说明（`rmtree` 永久删除 + `--force` 仍预检 corrupted）；best-practices.md §7.1 表格补 `task delete` 行，§6.1 坘 6 和附录 DO 清单同步。
- **`_safe_mkdir` 注释精度化（P3-3）**：L251 注释从 “Must be a regular file” 改为 “A regular file or a symlink-to-file”，准确描述 `cur.exists()` 的匹配范围（symlink-to-file 也返回 True）。
- 文档行数 1857 → 1859（注释扩展净增 2 行）。

### 改进（第 15 轮 oracle-reviewer）

第 15 轮审查 0 P1 / 0 P2 / 1 项 P3。连续 6 轮（10/11/12/13/14/15）0 P1，连续 4 轮（12/13/14/15）0 P2，代码核心契约跨调用者追踪全部成立，维护收敛态正式确认。

- **`_check_current_task` 改 idx 模式（P3-1）**：L1684 裸 `problems.pop()` 改为 `idx = len(problems) - 1` + `problems.pop(idx)`，与 `_check_developer_file` / `_check_required_subdirs` / `_check_workspace_dir` / `_check_archive` / `_check_journal` / `_check_journal_numbering` / `_check_task_integrity` / `_check_precommit` 8 处约定一致。完成 doctor 9 项检查全量化。零功能影响（现存调用路径中间无其他 append），防未来插入新检查项时 pop 移除错误条目。
- 文档行数 1859 → 1864（注释净增 5 行）。

### 改进（第 16 轮 oracle-reviewer）

第 16 轮审查 0 P1 / 0 P2 / 2 项 P3。连续 7 轮（10/11/12/13/14/15/16）0 P1，连续 5 轮（12/13/14/15/16）0 P2。第 13/14/15 轮历史修复全部回归干净，项目进入深度维护收敛态。

- **`write_json` 走向 `_safe_mkdir`（P3-A）**：L209-218 内部 `path.parent.mkdir(parents=True, exist_ok=True)` 改为 `_safe_mkdir(path.parent)`，防御深度统一。现存调用点（task.json / .current-task / .developer 写入）均能传递良好父目录，但该改动为未来调用点提供隐式保障。
- **`_safe_mkdir` 根路径边界补注释（P3-B）**：L247-252 补 "Root walk bound" 段，说明 `while cur != cur.parent` 循环在文件系统根自然终止、`p` 本身为 file 仍被处理、函数从不触碰目录（仅 unlink 文件）。消除 "`cur != cur.parent` 为何不是 `True`无限循环" 谜圈。
- 文档行数 1864 → 1878（注释净增 14 行）。

### 文档（第 17 轮 oracle-reviewer）

第 17 轮审查 0 P1 / 0 P2 / **0 P3** —— 5 个审计维度全部 0 发现（连续 8 轮 10-17 0 P1 / 连续 6 轮 12-17 0 P2）。本轮无代码逻辑变更，仅做 docs 同步：

- **`best-practices.md` 新增 §17 oracle-reviewer 实战经验沉淀（+107 行）**：6 子节——17.1 跨调用者追踪清单（5 个对称严格模式）、17.2 事件驱动审查原则（场景判别表）、17.3 数字同步纪律（5 处文档 grep + SearchReplace 工作流）、17.4 防御深度统一模式（`_safe_mkdir` 评判标准 4 维度）、17.5 验证命令清单（CI / 局部 / 跨调用者 grep 三档）、17.6 收敛态判定标准（4 阶段 + 合并 / 拆分阈值）。
- **§16 决策清单新增 7 条实战经验**：跨文件数字同步 / `_safe_mkdir` 防御深度 / idx 模式 pop / CHANGELOG 锚点日期 / 1700 行后审视单文件架构 / 局部测试 vs 全量 / 跨调用者追踪后才能宣称深度收敛。
- **数字同步修正**：本轮文档更新中发现 best-practices.md L3 / L812 行数 1879 → 1878，余量 121 → 122（之前 §17 写入时 wc -l 误读 1 行；实际 1878 行）。
- 文档变更范围：best-practices.md 943 → 943 行（仅 2 处数字修正，行数不变）；CHANGELOG.md 323 → 332 行（+9 行新增 entry）；trellis.py 1878 → 1878 行（无代码逻辑变更）。

### 改进（第 19 轮 oracle-reviewer）

第 19 轮审查（聚焦正确性 + 连贯性）0 P1 / **1 P2** / 6 P3。连续 9 轮（10-18）0 P1 后**首次重新发现 P2**——文档层回归：第 14 轮 P3-2 文档同步时在 exit-codes.md + best-practices.md 错误描述 `task delete --force` 为"仍预检 corrupted"，潜伏 5 轮。代码与测试一致：`task delete --force` 跳过 corrupted 预检直接 rmtree（exit 0），是显式的安全语义。

本轮修复 1 P2 + 6 P3 + 3 backlog（共 10 项），其中：
- **P2-1**：exit-codes.md:41 改"仍预检 corrupted"为"显式跳过 corrupted 预检 + 直接 rmtree（exit 0）"；best-practices.md:408 §7.1 表格对齐，注脚说明与代码 1:1；CHANGELOG 第 9 轮 F63 条目保持原状（一直是事实正确）。
- **P3-1**：`resolve_task_dir` 在 `tasks/` 缺失时返回 `None` 并打 `trellis: tasks/ missing ...` 红字错误 + exit 1（修复"指向缺失任务目录"错误信息误导）；新增 `test_task.py::test_resolve_task_dir_handles_missing_tasks_dir` 锁回归。
- **P3-2**：workflow-checklist.md §3 新建子目录措辞改为硬拒绝（"`trellis` 不会在 `tasks/` 缺失时自动 mkdir"）。
- **P3-3**：best-practices.md §7.1 时间戳表 `cancelled`/`finished` 措辞统一为"自动保留 30 天后清理"。
- **P3-4**：exit-codes.md `cmd_context` 合规表措辞与设计意图对齐。
- **P3-5**：usage-guide.md §8 delete 教程语义对齐：`--force` 章节明确说明"绕过 corrupted 预检" + 修复建议增加 `doctor` 优先。
- **§17.1 backlog**：4 处锚点修正（行号→符号名 + "7 类"→"5 状态+9 转移" + "9 项全部"→"5 项有 fix" + "5 修复点"→"6 修复点+write_json"）。
- **write_json 注释 narrative**：3 调用点→2 调用点（task.json 走 `write_json`，`.current-task`/`.developer` 走 `write_text`）。
- 测试总数 165 → **166**（+1 P3-1 回归测试）；trellis.py 1878 → **1888** 行（净 +10）；best-practices.md 943 → **943** 行（净增补 0；§17.3 grep 行补 ~1888）。

### 新功能（WRAP 完整性 + 任务模板）

- **WRAP 阶段完整性检查（跨命令）**：`task finish` / `task archive` 现在非阻塞地提示未完成的 WRAP 工作（未勾选验收标准、未记录 session、未提交 spec）；`task list` 为 done 任务显示 ✓/⚠ 健康标记；`context` 展示最近 done 任务的 WRAP 状态；`doctor` 新增第 10 项检查（done 任务的 WRAP 完整性）。
- **`task create --template bug|feature|refactor`**：三种预填充 prd.md 模板。`bug`（复现 + 根因假设 + 回归测试）、`feature`（需求 + 验收标准）、`refactor`（范围 + 行为不变保证）。省略则用默认骨架。
- **归档任务健康标记**：`task list --all` 现在为已归档任务计算真实健康标记（✓/⚠），而不是硬编码绿色勾——归档不可逆，但信号保持诚实。
- **session 悬空指针保护**：当 `.current-task` 指向已删除的任务目录时，`session` 命令不再注入悬空的 Task 链接或将标题退化为裸目录名。
- **pre-commit hook WRAP 检查**：hook 新增非阻塞警告——如果最近 done 任务的 WRAP 阶段不完整（未勾选标准 / 未记录 session），commit 时提醒闭环。

### 改进（第 20 轮 oracle-reviewer 后续）

- **`_wrap_completeness_warnings` 去除 dead parameter**：参数 `task_dir` 从未被函数体使用（函数检查全局 `get_workspace_dir()` + `git_status_porcelain()`），导致 doctor 遍历多个 done tasks 时重复报告全局警告。修复：函数改为无参数，doctor 添加 `seen` set 去重。
- **pre-commit hook 注释编号对齐**：头部注释的检查编号与内联 `Check N` 编号不一致（header 从 1 开始含 .trellis-lite 初始化，inline 从 1 开始是 doctor），统一为 0（初始化静默跳过）+ 1-3（doctor / planning / WRAP）。

### 文档（全量数字同步）

- 行数 1888 → **2130**（8 处：README.md / trellis-cli.md / best-practices.md / design.md ×2 / plans/ ×2）。
- 测试数 166 → **191**（7 处：README.md / best-practices.md / usage-guide.md ×2 / design.md / plans/ ×2）。
- doctor 检查数 9 → **10** 项（4 处：trellis-cli.md ×2 / installation-guide.md / design.md / usage-guide.md）。
- §17.6 拆分阈值更新：1700 / 1900 → **2000 / 2300**（与当前 2130 行 + 2026 实际增长率匹配）。
- §17.3 grep 模板同步：补 `~2129` / `~2130` / `190 个` / `191 个`。
- trellis-cli.md 补 `--template bug|feature|refactor` 命令参考（命令总览 + 参数表 + 使用说明）。
- trellis-cli.md doctor 检查清单补第 10 项（WRAP 完整性）。
- usage-guide.md 测试表格更新各模块测试数（test_task 52→67 / test_session 10→14 / test_context_specs_help 12→14 / test_doctor 24→26 / test_precommit 4→6）。
- plans/trellis-lite-process-quality-review.md 修复内部测试数矛盾（design.md 165 vs best-practices.md 166 → 统一为 191）。

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
4. 跑 `python3 -m unittest tests.test_init tests.test_install tests.test_precommit tests.test_session tests.test_slugify_fuzz tests.test_task tests.test_doctor tests.test_context_specs_help tests.test_status_machine tests.test_usage_consistency` 确认全绿
5. `git tag 0.x.y` 并 `git push --tags`

### 不放进 CHANGELOG 的内容

- 内部重构（除非改外部行为）
- 测试工具调整
- 注释、空白
- 依赖升级（除非影响用户）

---

[Unreleased]: #unreleased---2026-08-07
[0.6.9]: #069---2026-07-26
[0.6.0]: #060---2026-07-12
