# Trellis Lite — trellis.py 完整使用指南

> 配套文档：[README.md](../README.md) · [installation-guide.md](installation-guide.md) · [usage-guide.md](usage-guide.md) · [best-practices.md](best-practices.md) · [platforms.md](platforms.md) · [design.md](design.md) · [exit-codes.md](exit-codes.md)

> trellis.py 是 Trellis Lite 的**唯一可执行文件**（~1888 行，纯 Python 标准库，零外部依赖）。
> 本文档是完整的命令参考 + 场景化使用流程。

---

## 一、快速上手

```bash
# 所有命令统一入口（在安装过 Trellis Lite 的项目内执行）
python3 .trellis-lite/scripts/trellis.py <command>

# 查看帮助
python3 .trellis-lite/scripts/trellis.py help
python3 .trellis-lite/scripts/trellis.py -h
```

### 命令总览

```
trellis.py
├── init <name>          # 初始化开发者身份（唯一能在无 .trellis-lite 时运行的命令）
├── task                 # 任务管理（8 个子命令）
│   ├── create "<title>" [--slug <s>] [--replace]
│   ├── start <name>
│   ├── current
│   ├── finish
│   ├── archive <name>
│   ├── cancel <name>
│   ├── list [--all]
│   └── delete <name> [--force]
├── session --title "T" --summary "S" [--commit <hash>]
├── context              # AI 跨会话恢复入口（输出完整上下文）
├── specs                # 列出 spec 文件
├── doctor [--fix]       # 9 项健康检查 + 自愈
├── version              # 版本号
└── help / -h / --help   # 帮助
```

---

## 二、命令参考（按功能分组）

### 1. 初始化

#### `init <name>`

设置开发者身份，创建完整目录结构。

```
Usage: trellis.py init <your-name>
```

**行为**：
1. 创建 `.trellis-lite/tasks/archive/`、`.trellis-lite/spec/`
2. 创建 `.trellis-lite/workspace/<name>/`（含 `index.md` + `journal-1.md`）
3. 写入 `.trellis-lite/.developer`（`name=<name>`）
4. 创建 spec README（模板）

**成功输出**：

```
✓ Trellis Lite initialized for 'yourname'
  Workspace: /path/to/project/.trellis-lite/workspace/yourname
  Specs:     /path/to/project/.trellis-lite/spec
  Tasks:     /path/to/project/.trellis-lite/tasks
```

**注意事项**：
- 是**唯一**在 `.trellis-lite/` 不存在时也能运行的命令
- 重跑 `init` 会**覆盖** `.developer`（安装脚本 install.sh 则不会，见安装手顺）
- 其他命令在非 Trellis 项目根运行会报：`Error: not inside a Trellis Lite project. Run 'init' first.`

---

### 2. 任务管理

#### `task create "<title>" [--slug <name>] [--replace]`

创建新任务目录 + prd.md 模板，并自动设为当前任务。

```
Usage: trellis.py task create "<title>" [--slug <name>] [--replace]
```

| 参数 | 说明 |
|---|---|
| `"<title>"` | 任务标题（可含空格；自动剥离一对匹配的引号） |
| `--slug <name>` | 自定义目录名（默认由 title 自动生成） |
| `--replace` | 显式接管已有活跃任务（旧任务自动置为 done） |

**Slug 生成规则**：
- ASCII 标题 → `kebab-case`（如 "User Login API" → `user-login-api`）
- 中文等非 ASCII 标题 → `t-<md5前6位>`（如 `t-8f3a2b`）

**同日去重**：同一天同名任务自动追加 `-2`、`-3`（如 `08-08-login-2`）。

**活跃任务冲突**（"one task at a time" 规则）：

```bash
# 已有活跃任务时，默认拒绝
Refusing to create: '.trellis-lite/tasks/08-08-login' is still the active task.
Run 'task finish' or 'task cancel' first, or pass --replace to take over.
# 退出码 1，文件夹不创建

# 显式接管
$ trellis.py task create "新功能" --replace
Note: replaced active task '08-08-login' with '08-08-new-feature'.
✓ Task created: 08-08-new-feature
```

**成功输出**：

```
✓ Task created: 08-08-user-login
  Path: /path/to/project/.trellis-lite/tasks/08-08-user-login
  Status: planning
  Active: yes (auto-set)
```

**生成的文件**：
- `task.json` — 元数据（title / slug / status=planning / created / branch）
- `prd.md` — 需求文档模板（Goal / Requirements / Acceptance Criteria / Notes）

#### `task start <name>`

将任务状态置为 `in_progress`，并设为当前任务。

```
Usage: trellis.py task start <name>
```

**行为**：
- 支持简写：`task start login` 可匹配 `08-08-login`（按 `MM-DD-<name>` 字面后缀匹配）
- 其他 in_progress 任务存在时输出单条汇总警告
- **幂等**：已 in_progress 的任务重复 start 是安全 no-op

```bash
# 其他任务仍在进行时
Warning: 1 other task(s) still in_progress — one task at a time (08-08-oldtask).
Run 'task finish' or 'task cancel' to clean up.

# 已激活任务重复 start
Note: '08-08-login' is already in_progress.

# 终态任务拒绝启动
Error: cannot start a task in terminal state 'archived'. Forward-only transitions are enforced.
```

**成功输出**：

```
✓ Task started: 08-08-login
  Status: in_progress
```

#### `task current`

显示当前活跃任务。

```
Usage: trellis.py task current
```

**输出**：

```
Active task: .trellis-lite/tasks/08-08-login
  Title:  用户登录
  Status: in_progress
  ✓ prd.md
  — design.md
```

- 无活跃任务 → `No active task.`（返 0，读取类命令空状态不报错）
- task.json 损坏 → 黄色警告 + 提示 `doctor --fix`

#### `task finish`

将**当前活跃任务**置为 `done`，清除活跃指针。

```
Usage: trellis.py task finish
```

**行为**：
- 无活跃任务 → `No active task to finish.`（**返 1**，语义错误）
- 工作树有未提交改动 → 黄色警告（不阻止）
- 终态任务 → 拒绝（指针需手动清理）
- 已 done 任务重复 finish → `Note: already done — clearing the active pointer`

**成功输出**：

```
✓ Task finished: .trellis-lite/tasks/08-08-login
  Run 'task archive <name>' when ready to archive.
```

#### `task archive <name>`

将任务移动到 `tasks/archive/YYYY-MM/`（按当前月份归档）。

```
Usage: trellis.py task archive <name>
```

**行为**：
- 目标位置自动创建 `YYYY-MM/` 月份目录
- 同名冲突自动追加 `-2`（防止嵌套）
- 若归档的是当前活跃任务，自动清除活跃指针
- **拒绝 cancelled 任务**（终态）：

```bash
Refusing to archive: '08-08-xxx' is cancelled.
Cancelled is a terminal state (ALLOWED_TRANSITIONS).
Use 'task delete --force 08-08-xxx' to remove it, or create a new task if you want to redo the work.
```

**成功输出**：

```
✓ Task archived: 08-08-login
  → /path/to/project/.trellis-lite/tasks/archive/2026-08/08-08-login
```

#### `task cancel <name>`

放弃任务，状态置为 `cancelled`，**目录保留**用于历史记录。

```
Usage: trellis.py task cancel <name>
```

**行为**：
- 若取消的是当前活跃任务，自动清除活跃指针
- **拒绝 archived 任务**（终态）：
  ```
  Refusing to cancel: '08-08-xxx' is archived.
  Archived is a terminal state (ALLOWED_TRANSITIONS).
  ```
- 已 cancelled 重复取消 → `Note: '08-08-xxx' is already cancelled.`（幂等，返 0）

**成功输出**：

```
✓ Task cancelled: 08-08-xxx
  Directory kept in tasks/. Delete it manually if unneeded.
```

#### `task list [--all]`

列出任务。默认仅活跃任务；`--all` 包含归档任务。

```
Usage: trellis.py task list [--all]
```

**输出格式**：

```
Active Tasks:
  → 08-08-login      [in_progress]  用户登录
    08-05-refactor   [done]         重构认证模块
    08-03-old        [planning]     旧需求

All Tasks (active + archive):
  → 08-08-login      [in_progress]  用户登录
    08-08-old        [cancelled]    放弃的任务
    08-02-history    [archived]     历史任务
```

- `→` 绿色箭头 = 当前活跃任务
- 颜色语义：`in_progress` 绿色 / `planning` 黄色 / `done`+`archived`+`cancelled` 暗色
- task.json 损坏 → 状态显示 `[?]`

#### `task delete <name> [--force]`

**永久删除**任务目录（不可逆！）。

```
Usage: trellis.py task delete <name> [--force]
```

| 参数 | 说明 |
|---|---|
| 默认 | 只允许删除 `cancelled` 状态的任务 |
| `--force` | 跳过状态检查（最后手段，直接删除） |

**默认拒绝非 cancelled 任务**：

```bash
Refusing to delete task with status 'in_progress'. Cancel it first (task cancel 08-08-login) or use --force.
  Tip: 'task current' still shows this task; run 'task cancel' first (or 'task finish' if in_progress).
```

**成功输出**：

```
✓ Task deleted: 08-08-xxx
```

**安全机制**：
- 删除前自动清除指向该任务的活跃指针
- 默认拒绝 corrupted task.json（防误删）；`--force` 是用户显式承担风险的逃生口

---

### 3. 会话记录

#### `session --title "T" --summary "S" [--commit <hash>]`

向当前日志追加一条会话记录。

```
Usage: trellis.py session --title "Title" --summary "Summary"
```

| 参数 | 说明 |
|---|---|
| `--title "T"` | **必填**。标题（动词 + 范围，如 "实现用户登录"） |
| `--summary "S"` | 可选。做了什么 / 关键决定 / 已知遗留（省略则写 `(no summary)`） |
| `--commit <hash>` | 可选。关联 commit，支持 4–64 位 hex（SHA-1 40 位 / SHA-256 64 位） |

**commit 校验**：非 hex 或长度不符 → 拒绝 + exit 1：

```bash
Error: 'abc' doesn't look like a git SHA (4-64 hex chars). Refusing to record a session with a bogus commit hash.
```

**journal 轮转**：当前 journal 超过 2000 行自动创建 `journal-N+1.md`。

**成功输出**：

```
✓ Session recorded: 实现用户登录
  Journal: journal-1.md
  Total sessions: 12
```

**journal 格式**：

```markdown
## 2026-08-08 14:30 — 实现用户登录

**Commits**: `abc1234`

用 JWT 实现了登录接口，spec 中新增了 token 过期策略规则。
```

---

### 4. 上下文与规范

#### `context`

输出完整的会话上下文（**AI 跨会话恢复的入口**，AI 自动调用）。

```
Usage: trellis.py context
```

**输出结构**：

```
============================================================
  Trellis Lite — Session Context
============================================================
  Developer: yourname
  Active task: .trellis-lite/tasks/08-08-login
    Title:  用户登录
    Status: in_progress
    Artifacts: ✓ prd.md — design.md
  Branch: main
  Dirty files: 3
------------------------------------------------------------
  Recent commits:
    abc1234 第 18 轮审查修复
    def5678 新增功能
  Specs: 2 file(s)
    - README.md
    - TEMPLATE.md
  Last session: 实现用户登录  (journal-2.md)
============================================================
```

**包含**：开发者 / 活跃任务（含损坏警告）/ 分支 / 脏文件数 / 最近 5 条 commit / 前 5 个 spec + 计数 / 最近 journal 标题。

#### `specs`

列出所有可读的 spec 文件。

```
Usage: trellis.py specs
```

**输出**：

```
Available Specs:
  README.md
  api-patterns.md
  conventions.md
  gotchas.md
```

无 spec → `No specs found. Write your first spec in spec/README.md`（返 0）。

---

### 5. 诊断

#### `doctor [--fix]`

9 项健康检查 + `--fix` 自动修复。**项目状态不正常时第一个该跑的命令**。

```
Usage: trellis.py doctor [--fix]
```

**9 项检查清单**：

| # | 检查项 | 严重度 | --fix 可修 |
|---|---|---|---|
| 1 | `.trellis-lite/` 存在 | Problem（缺失则早退） | — |
| 2 | `.developer` 存在且含 `name=...` | Problem / Warning | ✅ |
| 3 | `tasks/`、`tasks/archive/`、`spec/` 存在 | Warning | ✅ |
| 4 | `workspace/<dev>/` 存在 + 至少 1 个 journal | Warning | ✅ |
| 5 | `.current-task` 指针有效 + task.json 可读 | Problem / Warning | ✅（仅 stale 指针） |
| 6 | 所有任务目录（含归档）task.json 完整 | Problem | — |
| 7 | journal 编号从 1 开始、无 gap | Warning | — |
| 8 | Python ≥ 3.9 | Problem | — |
| 9 | 脏文件计数 | 仅提示 | — |

**退出码**：
- 有 Problem → exit 1（`✗ Found N problem(s):`）
- 仅有 Warning → exit 0（`⚠ N warning(s):`）
- 全部通过 → exit 0（`✓ All checks passed.`）

**--fix 能修**：恢复 .developer（从唯一 workspace 子目录推断身份）、补齐缺失子目录、创建 journal-1、清理 stale 指针。
**--fix 不修**：corrupted task.json（需手动或 `task delete --force`）、journal 编号 gap。

---

### 6. 元信息

#### `version`

```
trellis-lite 0.6.9
```

#### `help` / `-h` / `--help`

完整帮助列表 + 工作流提示：

```
Trellis Lite
v0.6.9 — Single-file task & session manager for agile solo developers.

Commands:
  init <name>              Initialize developer identity
  task create "<title>"    Create a new task (--slug <s>, --replace to take over)
  ...
  version                  Print version and exit

Workflow: init → task create → task start → code → task archive → session
```

---

## 三、完整使用流程（场景式）

### 场景 1：从零开始一个任务（完整生命周期）

```bash
# ─── Step 1: 初始化（首次） ───
python3 .trellis-lite/scripts/trellis.py init yourname

# ─── Step 2: 创建任务 ───
python3 .trellis-lite/scripts/trellis.py task create "实现用户登录" --slug user-login
# → 生成 .trellis-lite/tasks/08-08-user-login/{task.json, prd.md}

# ─── Step 3: 写 PRD 并确认（编辑 prd.md） ───
# 补全 Goal / Requirements / Acceptance Criteria / Notes

# ─── Step 4: 启动任务 ───
python3 .trellis-lite/scripts/trellis.py task start user-login
# → status: planning → in_progress

# ─── Step 5: 开发中（随时查看状态） ───
python3 .trellis-lite/scripts/trellis.py context
python3 .trellis-lite/scripts/trellis.py specs      # 找相关规范
python3 .trellis-lite/scripts/trellis.py task current

# ─── Step 6: 完成任务 ───
python3 .trellis-lite/scripts/trellis.py task finish
# → status: in_progress → done，清除活跃指针

# ─── Step 7: 归档（可选，完成后推荐） ───
python3 .trellis-lite/scripts/trellis.py task archive user-login
# → 移动到 tasks/archive/2026-08/08-08-user-login

# ─── Step 8: 记录会话 ───
python3 .trellis-lite/scripts/trellis.py session \
    --title "实现用户登录" \
    --summary "POST /api/login + JWT 签发。5 次错误锁定 30 分钟。" \
    --commit abc1234
```

### 场景 2：放弃 / 清理任务

```bash
# 放弃一个做了一半的任务（目录保留作历史）
python3 trellis.py task cancel 08-08-xxx
# → status: in_progress → cancelled

# 永久删除（先 cancel，默认只允许删 cancelled 状态）
python3 trellis.py task delete 08-08-xxx
# → 删除目录

# 强制删除任意状态（最后手段）
python3 trellis.py task delete 08-08-xxx --force
```

### 场景 3：切换任务

```bash
# 方式一：正常切换（先完成旧的）
python3 trellis.py task finish          # 完成当前
python3 trellis.py task start new-task  # 启动新的

# 方式二：显式接管（旧任务自动置为 done）
python3 trellis.py task create "新功能" --replace
# Note: replaced active task '08-08-old' with '08-08-new'.
```

### 场景 4：跨会话恢复（隔天/隔周回来）

```bash
# AI 恢复流程（全部只读，不会改动代码）：
python3 trellis.py context              # ① 看整体状态（开发者/任务/分支/日志）
python3 trellis.py task current         # ② 看当前任务详情
# ③ 读 .trellis-lite/tasks/<name>/prd.md 回顾需求
# ④ git log --oneline -10 看上次提交
# ⑤ 继续实现剩余 acceptance criteria
```

### 场景 5：健康诊断

```bash
# 日常体检（每天早上）
python3 trellis.py doctor

# 出现不可解释的问题 → 自愈
python3 trellis.py doctor --fix

# doctor 输出示例（有 Problem 时 exit 1）
✗ Found 2 problem(s):
  - .developer missing
  - orphan task dir (no task.json): tasks/08-08-broken

Run with --fix to auto-repair common issues, or fix manually.
```

---

## 四、退出码速查

| 命令 | 成功 | 失败/拒绝 | 说明 |
|---|---|---|---|
| `init` | 0 | 1 | — |
| `task create` | 0 | 1 | 活跃任务冲突 / 空标题 |
| `task start` | 0 | 1 | 终态任务 / corrupted |
| `task current` | 0 | 0 | 读取类，空状态也返 0 |
| `task finish` | 0 | **1** | 无活跃任务 / corrupted / 终态 |
| `task archive` | 0 | 1 | cancelled / corrupted |
| `task cancel` | 0 | 1 | archived / corrupted |
| `task list` | 0 | 0 | 读取类，空状态也返 0 |
| `task delete` | 0 | 1（默认非 cancelled） | `--force` 旁路 |
| `session` | 0 | 1 | 缺 title / commit 格式错 |
| `context` | 0 | 0 | 读取类 |
| `specs` | 0 | 0 | 读取类 |
| `doctor` | 0 | **1（有 Problem）** | 仅 Warning 返 0 |
| `version` / `help` | 0 | — | — |

> **可逆性原则**：不可逆操作失败必须中止（mutating 命令遇 corrupted 一律返 1）；可恢复操作可降级继续（读取类命令空状态返 0）。完整语义见 [exit-codes.md](exit-codes.md)。

---

## 五、常用命令组合模式

### 完成一个任务的标准收尾

```bash
python3 trellis.py task finish \
  && git add -p && git commit -m "feat: 实现用户登录" \
  && python3 trellis.py task archive user-login \
  && python3 trellis.py session --title "实现用户登录" --summary "..." --commit $(git rev-parse HEAD)
```

### CI / 脚本安全管道

```bash
set -e
# finish 失败明确中止（无活跃任务 / corrupted 时返 1）
python3 trellis.py task finish
```

### 检查是否有某任务

```bash
# 读取类命令空状态返 0 — 用输出内容判断，不要用退出码
if python3 trellis.py task list | grep -q "user-login"; then
    echo "task exists"
fi
```

---

## 六、状态机速查

```
planning ──(task start)──→ in_progress ──(task finish)──→ done ──(task archive)──→ archived
     │                         │                                                    │
     │                         └────────────────────────────────────────────────────┘
     │                    （也可直接 archive，跳过 finish）
     │
     └─ planning / in_progress ──(task cancel)──→ cancelled（目录保留）
done ──(task cancel)──→ cancelled（允许"改主意"）

planning ──(task archive)──→ archived（可直接归档）
planning ──(task cancel)──→ cancelled
in_progress ──(task cancel)──→ cancelled
```

| 起始状态 | 允许转移 |
|---|---|
| `planning` | `in_progress` / `done` / `archived` / `cancelled` |
| `in_progress` | `done` / `archived` / `cancelled` |
| `done` | `archived` / `cancelled` |
| `archived` | （终态） |
| `cancelled` | （终态） |

**关键规则**：
- **Forward-only**：除 `done → cancelled` 外不能回滚
- **终态不可转移**：`archived` / `cancelled` 是永久状态
- **幂等**：同一状态重复操作是安全 no-op（不重写文件、不更新时间戳）