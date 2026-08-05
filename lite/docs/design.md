# Trellis Lite — 设计原理与实现

> 配套文档：[README.md](../README.md) · [usage-guide.md](usage-guide.md) · [best-practices.md](best-practices.md)

## 一、设计原理

### 核心问题

原版 Trellis 为**多平台、多 agent 协作**的团队场景设计，功能强大但复杂度高：28 个 Python 脚本、4 阶段工作流、20+ 平台适配层、Channel 事件溯源协作、跨会话 Memory 检索、JSONL 上下文清单。对于**个人开发者 + Qoder 单平台**来说，大部分是死重。

### 五条设计原则

| 原则 | 原版做法 | Lite 做法 | 动机 |
|---|---|---|---|
| **一个脚本搞定一切** | 28 个 Python 脚本分散在 `scripts/`, `task_store.py`, `task_context.py`... | 单文件 `trellis.py`（~1330 行） | 降低安装、维护、理解成本 |
| **零外部依赖** | pnpm workspace + Node CLI + 多平台运行时 | 纯 Python 3.9+ 标准库 | 个人开发者不想装一堆依赖 |
| **文件即数据库** | JSON 存任务 + JSONL 上下文清单 | JSON 存任务，Markdown 存日志 | 去掉中间层，AI 直接消费 |
| **AI 直接消费** | AI 读 JSONL 上下文清单（`implement.jsonl`/`check.jsonl`，按任务圈定 spec/research 文件） | AI 直接读 PRD + spec 文件 | 去掉中间格式，减少信息损耗（代价：丢失按任务精准注入） |
| **保留 Sub-agent** | Channel 事件溯源协作 + implement/check sub-agent | Qoder 原生 `GeneralPurpose` / `CodeReview` | 大任务仍可并行分发 |

### 核心取舍

```
 砍掉                          保留
 ─────────────────────────────────────────────
 Channel 事件溯源协作            Sub-agent 分发（Qoder 原生）
 Memory 跨会话检索              文件型会话日志（Markdown）
 JSONL 上下文清单               AI 直接读 markdown
 4 阶段工作流                   3 阶段（PLAN→CODE→WRAP）
 20+ 平台适配                   仅 AGENTS.md
 多文件脚本架构                 单文件 Python
```

---

## 二、架构设计

### 整体结构

```
AGENTS.md                         ← Qoder 入口（AI 读到的第一个文件）
.trellis-lite/
├── scripts/
│   └── trellis.py                ← 单文件任务管理器（唯一可执行代码）
├── workflow.md                   ← 3 阶段工作流定义（纯文档）
├── skills/                       ← AI 行为指导（纯 markdown，非代码）
│   ├── brainstorm.md             ← Phase 1: 需求发现
│   ├── before-dev.md             ← Phase 2: 编码前加载 spec
│   ├── check.md                  ← Phase 2: 质量验证
│   └── update-spec.md            ← Phase 3: 经验沉淀
├── spec/                         ← 项目编码规范（"可执行契约"）
│   └── README.md                 ← 规范编写指南
├── tasks/                        ← 活跃任务
│   └── archive/                  ← 已归档（按年月分子目录）
├── workspace/<dev>/              ← 开发者会话日志
│   ├── index.md
│   └── journal-N.md              ← 自动轮转（每 2000 行）
├── .developer                    ← 开发者身份指针
└── .current-task                 ← 当前活跃任务指针
```

### 数据流

```
 用户请求
    │
    ▼
 Qoder 读取 AGENTS.md ──→ 识别 Lite 工作流
    │
    ▼
 trellis.py context ──→ 输出当前状态（开发者/任务/分支/git）
    │
    ▼
 Phase 1: PLAN
    task create → 生成 tasks/MM-DD-slug/{task.json, prd.md}
    填写 prd.md → AI 和用户共同确认需求
    task start → status: planning → in_progress
    │
    ▼
 Phase 2: CODE
    specs → 读 spec/*.md 获取编码规范
    implement → 直接写 或 分发 GeneralPurpose agent
    check → 手动检查 或 分发 CodeReview agent
    │
    ▼
 Phase 3: WRAP
    update-spec → 经验写入 spec/*.md
    task archive → 移动到 tasks/archive/YYYY-MM/
    session → 追加到 workspace/<dev>/journal-N.md
```

---

## 三、关键实现

### 3.1 单文件设计（`trellis.py`）

全部功能集中在一个 ~1330 行文件中，按功能分区：

| 分区 | 行数 | 职责 |
|---|---|---|
| Constants | ~20 | 目录名、文件名、ANSI 颜色 |
| Path helpers | ~50 | `get_repo_root()` 向上查找 `.trellis-lite/` |
| Slugify | ~15 | ASCII → kebab-case，非 ASCII → md5 hash |
| JSON helpers | ~15 | `read_json`（带异常保护）/ `write_json` |
| Git helpers | ~35 | `status`/`log`/`branch`（subprocess + try/except） |
| Current task | ~25 | `.current-task` 文件指针（无状态管理器） |
| cmd_init | ~50 | 目录创建 + 名称校验 |
| cmd_task | ~310 | create/start/current/finish/archive/cancel/list/delete |
| cmd_session | ~80 | 日志追加 + 自动轮转 |
| cmd_context | ~85 | 汇总输出 |
| cmd_specs | ~35 | 列出 spec 文件 |
| cmd_doctor | ~50 + 9 × `_check_*` | 9 项自检 + `--fix` 自动修复（编排函数 + 独立 check 函数） |
| cmd_version + help | ~30 | 版本号 + 命令分发 |

### 3.2 任务系统

**目录结构**：`tasks/MM-DD-slug/`，每个任务一个目录：

```
tasks/07-26-login-api/
├── task.json    ← 元数据（title, status, created, branch, started, finished）
├── prd.md       ← 需求文档（AI 和用户共同维护）
└── design.md    ← 设计笔记（可选，复杂任务）
```

**状态机**：

```
planning ──(task start)──→ in_progress ──(task finish)──→ done ──(task archive)──→ archived
     │                         │                              │
     │                         │                              └──(task cancel)──→ cancelled（唯一允许的反向转移）
     │                         │                                                   cancelled = 终点；archive 可选
     └─────────────────────────┴──────── 也可以直接 archive（跳过 finish）─────────┘

planning / in_progress ──(task cancel)──→ cancelled（目录保留，不归档）
```

> **与原版的状态术语差异**：原版 Trellis 任务状态为 `planning → completed`（归档时置 `completed`），lite 细化为 `planning / in_progress / done / archived / cancelled` 五态。这是有意为之 — 为单人工作流提供更细的进度可见性（`task list` 可区分进行中/已完成/已放弃）。若未来迁移回原版，需做状态字段映射。

**时间戳约定**（`task.json` 字段）：

- `created`：任务记录创建时刻（`planning` 状态），由 `_task_create` 写入，永不修改。
- `started`：第一次切到 `in_progress` 的时刻，由 `task start` 写入。`planning` 任务上**该字段不存在**（任务是规划阶段、尚未开始）；这是正确语义，不是缺漏。
- `finished` / `archived` / `cancelled`：分别由 `task finish` / `task archive` / `task cancel` 写入对应时刻。

约定：每个时间戳对应**触发该 status 转移**的事件，详见 `set_status(task_dir, new_status, *, when=<field>)` helper。

**关键设计决策**：

- **文件指针而非状态管理器**：`.current-task` 只存一行文本（相对路径），没有锁、没有 session、没有并发控制 — 因为面向个人开发者，一个人不会同时操作两个任务。
- **Slug 自动生成**：ASCII 标题用 `re.sub(r"[^a-z0-9]+", "-", text.lower())`；CJK 等非 ASCII 标题用 `md5(text)[:6]` 生成 `t-xxxxxx` 格式，避免全部退化成 `task`。
- **同日去重**：`while task_dir.exists()` 循环自动追加 `-2`、`-3`。

### 3.3 Spec 系统

**核心理念**：spec 不是"文档"，而是**可执行契约**。

```markdown
## Rule: API Response Format
All API endpoints return `{ data, error, meta }`.

**Do:**
return { data: result, error: null, meta: { page: 1 } }

**Don't:**
return result  // bare return, no envelope
```

AI 在 Phase 2（CODE）开始前**必须读取相关 spec**，这不是建议而是硬约束。spec 在 Phase 3（WRAP）中被更新 — 把调试中学到的教训固化成规则，防止同类问题复发。

### 3.4 会话日志

**设计**：Markdown 追加式日志，每 2000 行自动轮转到下一个文件。

```markdown
## 2026-07-26 14:30 — 实现用户登录

**Commits**: `abc1234`

用 JWT 实现了登录接口，spec 中新增了 token 过期策略规则。
```

**为什么不做 Memory 系统**：原版 Memory（`packages/core/src/mem/`）是**跨会话检索 + 对话上下文提取**（`searchMemSessions`/`extractMemDialogue`），基于持久化的 Claude/Codex/OpenCode 会话做语义搜索。个人开发者通常不需要这种跨任务的语义检索 — 一个按时间排列的 Markdown 日志就够了，还能直接 `git diff` 查看历史。这是**能力降级**（丢失语义检索），但对单人场景收益低、成本高，取舍合理。

### 3.5 Sub-agent 分发

保留了原版最有价值的能力 — 大任务可以分发给专用 agent：

| Agent | 用途 | Prompt 要求 |
|---|---|---|
| `GeneralPurpose` | 实现代码 | 必须以 `Active task: <path>` 开头，先读 `prd.md` + specs |
| `CodeReview` | 质量检查 | 同上，检查 `git diff` 是否符合 spec + PRD |

---

## 四、健壮性保障

经过多轮审查与加固，修复了以下类别的问题：

| 阶段 | 类别 | 问题数 | 典型修复 |
|---|---|---|---|
| 第 1–2 轮代码审查 | 安全 | 3 | `--slug` 路径穿越、`init` 名称注入、`start/archive` 任务名路径穿越 |
| 第 1–2 轮代码审查 | 数据完整性 | 4 | JSON 损坏保护、archive 目录嵌套、同日任务碰撞、journal 轮转编号碰撞 |
| 第 1–2 轮代码审查 | 正确性 | 3 | CJK slug、状态更新遗漏、子串误匹配 |
| 第 1–2 轮代码审查 | 一致性 | 2 | 状态术语统一、git 命令统一 |
| 第 3 轮流程审查 | 流程 | 4 | skills 断链（workflow.md 内联路由）、commit 指引与 no-auto-commit 规则矛盾、新增 `task cancel` 放弃出口、start/finish 增加状态警告 |
| 用户加固（提交 7c7d059） | 语义 / UX | 5 | 拒绝任务名 `archive`（防归档自身容器）、glob → endswith 字面匹配避免 glob 注入、create 已有活跃任务时警告、title 引号配对剥离、README 平台表述精确化 |
| 第 4 轮体验增强（本轮） | UX / 文档 | 4 | `task list --all` 查看已归档任务、`--commit` 哈希格式校验、`context` 输出 spec 列表 + 最近 journal 摘要、workflow.md 增加 `.current-task` 并发警告 |
| 本轮（质量提升） | 测试 / CI | 2 | `lite/tests/` 123 个 unittest 覆盖全部命令（unittest 零依赖）；`.github/workflows/test.yml` 在 Python 3.9–3.13 矩阵上跑 py_compile + install.sh 烟测 + uninstall.sh 烟测 + unittest + coverage 报告；`trellis.py` 全量返回值类型注解（32/32）并补 14 个 cmd_* docstring |

---

## 五、运行测试与 CI

```bash
# 本地运行全部测试
python3 -m unittest discover -s lite/tests -t .

# 单独运行某个模块
python3 -m unittest lite.tests.test_task -v
```

CI 在 `.github/workflows/test.yml` 自动跑，矩阵 Python 3.9–3.13，每步包含：

1. `py_compile` 字节码编译
2. `install.sh` 烟测（默认 `--platforms all`）
3. `uninstall.sh` 烟测（拒绝空目标 + 完整卸载）
4. 跑全部 unittest（123 个）
5. coverage 报告（**仅 in-process 部分**：slugify 模糊测试 + 模块加载）

> **覆盖率 13% 的解释**：为保证测试隔离，全部 `cmd_*` 测试用 `subprocess.run` 启动独立 Python 进程。
> coverage.py 默认无法跨进程跟踪。如果要把覆盖率提升到 ≥70%，需要把核心测试改为 in-process
> （直接 `import trellis` 调用 `cmd_*` 函数）。本项目暂保留 subprocess 隔离，未做此重构——**测试数量与
> 行为覆盖**比百分数更重要（每条 CLI 路径都有 ≥1 个断言）。

## 六、适用场景与局限

| 适合 | 不适合 |
|---|---|---|
| 1 人 + AI 编码工具（Qoder / Claude Code / OpenCode / Cline）的项目 | 多人团队协作 |
| 需要 AI 遵循工作流但不想要重框架 | 需要 Channel 实时多 agent 协作 |
| 偏好文件系统而非数据库 | 需要复杂任务依赖/甘特图 |
| Python 3.9+ 环境 | 无 Python 环境（可未来用 Node 重写） |
