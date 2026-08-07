# Trellis Lite — 使用指南

> 完整示例：从安装到任务归档的全流程演示。
>
> 进阶：[best-practices.md](best-practices.md) — 任务分流、PRD/spec 写法、Sub-agent 策略。
>
> 任务级 checklist：[workflow-checklist.md](workflow-checklist.md) — 可复制到任务笔记的逐项打勾清单。

---

## 多平台支持

Trellis Lite 支持以下 AI 编码工具，核心工作流完全相同，只是入口文件不同：

| 平台 | 入口文件 | 原理 | 安装参数 |
|---|---|---|---|
| **Qoder** | `AGENTS.md` | 原生 | `--platforms qoder` |
| **OpenCode** | `AGENTS.md` | 原生兼容 AGENTS.md 标准 | `--platforms opencode` |
| **Claude Code** | `CLAUDE.md` | 通过 `@AGENTS.md` 导入语法桥接 | `--platforms claude` |
| **Cline** | `.clinerules/trellis-lite.md` | Cline 自动检测 `.clinerules/` 目录 | `--platforms cline` |
| **全部** | 以上所有 | — | `--platforms all`（默认） |

### 安装示例

```bash
# 全部平台（默认）
./install.sh . myname

# 仅 Claude Code
./install.sh . myname --platforms claude

# Qoder + Cline
./install.sh . myname --platforms qoder,cline
```

### 各平台 Sub-Agent 差异

核心工作流（PLAN → CODE → WRAP）和 `trellis.py` CLI 在所有平台完全一致。唯一差异是 sub-agent 分发方式：

| 平台 | Sub-Agent 机制 | 说明 |
|---|---|---|
| **Qoder** | `Agent` 工具 | `subagent_type: "GeneralPurpose"` 实现，`"CodeReview"` 审查 |
| **Claude Code** | `Task` 工具 | `subagent_type: "general-purpose"` 实现，`"code-reviewer"` 审查 |
| **OpenCode** | 内置 agent 系统 | 通过 `opencode.json` 配置自定义 agent |
| **Cline** | 无原生 sub-agent | 在主会话中直接实现，或通过 MCP 扩展 |

> 小/中等任务在所有平台都是主会话直接实现，sub-agent 仅影响大任务。

---

## 准备：让 AI 读到 Lite 指令

1. 确认项目根目录有对应平台的入口文件（见上表）。
2. 确认已运行 `install.sh` 生成了 `.trellis-lite/` 运行时。
3. 在你的 AI 工具中**开新会话** — 大多数工具在会话启动时静态读取入口文件一次，不支持热重载。

验证是否加载成功：在新会话中问 AI「你读到了哪些指令文件？」，应能识别出 Trellis Lite 指令。

---

## 场景演示：给 Trellis Lite 添加 `task delete` 命令

下面模拟一个真实任务从启动到归档的全过程。展示「你说什么 → AI 做什么」的对应关系。

### Phase 1: PLAN — 需求澄清与任务创建

**你说**：

> 给 trellis.py 加一个 `task delete` 命令，删除指定任务目录，需要二次确认，归档中的不能删。

**AI 收到后自动执行**：

```bash
# 1. 检查当前状态
python3 .trellis-lite/scripts/trellis.py context
```

AI 判断：这是**中等任务**（新增一个命令），需要建任务。

```bash
# 2. 创建任务
python3 .trellis-lite/scripts/trellis.py task create "Add task delete command" --slug add-delete-cmd
```

输出：

```
✓ Task created: 07-26-add-delete-cmd
  Path: .trellis-lite/tasks/07-26-add-delete-cmd
  Status: planning
```

**AI 主动写 PRD**（写入 `.trellis-lite/tasks/07-26-add-delete-cmd/prd.md`）：

```markdown
# PRD: Add task delete command

## Goal
Add a `task delete <name>` subcommand to trellis.py that removes a task directory.

## Requirements
- Delete `.trellis-lite/tasks/<task-dir>/`
- Require `--force` flag (or interactive y/N) for safety
- Refuse to delete archived tasks (under `archive/YYYY-MM/`)
- Refuse to delete the currently active task (must `finish` first)

## Acceptance Criteria
- [ ] `task delete <name>` prompts for confirmation
- [ ] `task delete <name> --force` skips prompt
- [ ] Active task → error: "finish or archive first"
- [ ] Archived task → error: "archived tasks cannot be deleted"
- [ ] Non-existent task → error: "task not found"
```

**AI 反馈给你**：

> PRD 已写入。要点：
> 1. 默认交互式确认，`--force` 跳过
> 2. 活动任务拒绝删除
> 3. 归档任务拒绝删除
> 确认开工吗？

**你说**：可以

```bash
# 3. 切到 in_progress
python3 .trellis-lite/scripts/trellis.py task start add-delete-cmd
```

---

### Phase 2: CODE — 读 spec → 写代码 → 检查

```bash
# 4. 读相关 spec
python3 .trellis-lite/scripts/trellis.py specs
```

AI 会主动读：
- `.trellis-lite/spec/README.md`（项目级规范）
- `lite/.trellis-lite/scripts/trellis.py`（要改的文件本身，了解现有命令结构）

然后实现代码（中等任务在主会话直接改即可）。AI 会：
1. 在 `trellis.py` 找到 `_task_archive` 旁边
2. 加 `_task_delete(args)` 函数
3. 在 subparser 区注册 `delete` 子命令
4. 加上 `--force` flag

**自检**：

```bash
python3 -c "import py_compile; py_compile.compile('.trellis-lite/scripts/trellis.py', doraise=True); print('PASS')"

# 端到端测试
python3 .trellis-lite/scripts/trellis.py task create "test-delete" --slug del-me
python3 .trellis-lite/scripts/trellis.py task delete del-me              # 应提示确认
python3 .trellis-lite/scripts/trellis.py task delete del-me --force      # 应删除
python3 .trellis-lite/scripts/trellis.py task delete nonexistent         # 应报错
```

---

### 大任务演示：使用 Sub-Agent

如果任务是「重构整个 trellis.py 把 argparse 换成 click」，AI 会用 sub-agent 分发：

**实现分发**（Qoder 示例）：

```
Agent(subagent_type="GeneralPurpose", prompt="""
Active task: .trellis-lite/tasks/07-26-argparse-to-click

Read these first:
- .trellis-lite/tasks/07-26-argparse-to-click/prd.md
- .trellis-lite/spec/README.md
- .trellis-lite/scripts/trellis.py (current implementation)

Task: Refactor trellis.py from argparse to click.
Constraints:
- Keep all existing commands and flags
- Zero external deps (use only stdlib)
- Run py_compile after.
""")
```

> Claude Code 中等价写法：`Task(subagent_type="general-purpose", ...)`。
> Cline 无原生 sub-agent，在主会话直接实现。

**审查分发**：

```
Agent(subagent_type="CodeReview", prompt="""
Active task: .trellis-lite/tasks/07-26-argparse-to-click

Review `git diff` against:
- .trellis-lite/tasks/07-26-argparse-to-click/prd.md
- .trellis-lite/spec/README.md

Auto-fix mechanical issues. Report anything substantive.
""")
```

---

### Phase 3: WRAP — 收尾

#### 3.1 更新 spec（如果有学到的东西）

比如这次发现「`shutil.rmtree` 前要先检查路径在 `.trellis-lite/tasks/` 内防穿越」，AI 会写入：

```markdown
# .trellis-lite/spec/security.md
## Path Safety
Before `shutil.rmtree`, always resolve and verify the path is inside the expected base dir.
```

即使「没有可更新的」，也要显式决定，不能跳过这一步。

#### 3.2 提交（必须问用户）

> 改动如下：
> - modified: `.trellis-lite/scripts/trellis.py` (+45 lines)
> - modified: `lite/.trellis-lite/scripts/trellis.py` (+45 lines)
>
> 提交吗？

**你说**：提交

```bash
git add .trellis-lite/scripts/trellis.py lite/.trellis-lite/scripts/trellis.py
git commit -m "feat(trellis): add task delete command with safety checks"
```

> AGENTS.md 第 101 行明文规定：**No auto-commit. Always ask the user before `git commit`.**

#### 3.3 归档 + 记录会话

```bash
python3 .trellis-lite/scripts/trellis.py task archive add-delete-cmd
python3 .trellis-lite/scripts/trellis.py session \
  --title "Add task delete command" \
  --summary "Added task delete with --force flag and path safety check. Updated spec/security.md." \
  --commit <hash>
```

---

## 对话语法速查

| 你想做的 | 自然语言示例 |
|---|---|
| 开新任务 | "我要做 X" / "加个功能 Y" |
| 看当前状态 | "现在在做什么任务？" / "继续" |
| 跳过任务系统 | "改个 typo，src.ts 第 10 行" |
| 中止任务 | "这个先放一放" / "归档吧" |
| 让 AI 自己跑 | "按 lite 流程走，做完为止" |
| 看 spec | "项目规范是什么？" |
| 看历史 | "上次 e2e-test 任务怎么解的？" → 读 journal |

---

## 任务分流规则

| 任务规模 | 处理方式 |
|---|---|
| **小任务**（typo、rename、单文件修复，< 5 分钟） | 跳过任务创建，直接改 |
| **中等任务**（新函数、bug 修复、小功能） | 创建任务，仅写 PRD |
| **复杂任务**（新模块、重构、跨文件功能） | 创建任务，写 PRD + design notes，可能用 sub-agent |

---

## 关键约定

1. **你不需要记命令** — 自然语言描述意图，AI 自己调用 `trellis.py`
2. **PRD 是契约** — AI 写完会给你看，确认才进入 CODE 阶段
3. **Sub-agent 自动** — 任务大时 AI 自己分发，不用你管
4. **不会自动 commit** — AGENTS.md 明文规定必须先问用户
5. **Spec 是活的** — 每次学到东西都会沉淀到 `.trellis-lite/spec/`
6. **One task at a time** — 一个时间只有一个活动任务

---

## 完整流程图

```
你说话
   ↓
AI 调 context 判断
   ↓
小? ──────────────→ 直接改
中/大? ↓
task create + PRD
   ↓
你确认 ←──── AI 写 PRD 给你看
   ↓
task start
   ↓
读 spec + 实现 (或分发 sub-agent)
   ↓
py_compile / 测试
   ↓
更新 spec + 问 commit
   ↓
archive + session
   ↓
✓ 任务闭环
```

---

## 自带测试套件

Trellis Lite 仓库自带 161 个 unittest 覆盖全部命令 + 安装脚本 + doctor + pre-commit hook + status machine + usage consistency，作为开发者和 CI 的回归保护。（install/uninstall 测试需 bash 4+，macOS 默认 bash 3.2 会自动 skip。）

```bash
# 从仓库根运行（注意：Python 3.9+ 需要 `tests.` 包前缀，相对 import 才能工作）
python3 -m unittest tests.test_init tests.test_task tests.test_session \
                  tests.test_doctor tests.test_precommit tests.test_install \
                  tests.test_slugify_fuzz tests.test_context_specs_help \
                  tests.test_status_machine tests.test_usage_consistency

# 运行某个模块
python3 -m unittest tests.test_task -v
```

| 测试文件 | 测试数 | 覆盖范围 |
|---|---|---|
| `test_init.py` | 7 | 目录创建、校验、幂等 |
| `test_task.py` | 49 | create / start / finish / archive / cancel / list / delete，含路径穿越、CJK slug、连号保护、幂等重启、corrupted `task.json` 拒绝（F44-F53）、`--replace` 自动关闭旧任务及其边界（F49，P3-5a）、`--force` 绕过 corrupted 含指针清理断言（F63，P3-5b）、finish 终态分层报错含 archived 分支（P3-4，P3-H）、cancel 幂等清指针（第 10 轮 P3-A） |
| `test_session.py` | 9 | journal 追加、commit SHA 校验（合法/非法/多长度）、未初始化、日志轮转、非编号文件过滤 |
| `test_context_specs_help.py` | 12 | repo-root 守卫(4) / context(4，含 corrupted 活跃任务 warning) / specs(2) / help(2，含描述列对齐护栏 P3-E) |
| `test_install.py` | 15 | 默认 / claude / qoder+cline / 运行时路径清理 / uninstall 全部路径（含 O9/O11/O14/O16/O17） |
| `test_doctor.py` | 24 | 9 项健康检查、`--fix` 自愈、stray-file 恢复（F46）、archive 递归完整性（F54）、corrupted 活跃任务（F55）、developer 恢复（含 no-name 分支 P2-1）、orphan workspace 警告正/负向（P3-5c/P3-B）、终态指针 warning（P3-A） |
| `test_precommit.py` | 4 | hook 安装/卸载、`set -e` 兼容性、trellis marker 锚定 |
| `test_slugify_fuzz.py` | 6 | CJK / 表情 / 长串 / 边界字符的 slug 化与防 glob 注入 |
| `test_status_machine.py` | 20 | `ALLOWED_TRANSITIONS` 常量 + `set_status` 行为（含 corrupted 与并发场景的契约边界） |
| `test_usage_consistency.py` | 15 | USAGE 字典与端到端 `cmd_*` 的 usage 输出对齐 |

CI：`.github/workflows/test.yml` 在 Python 3.9–3.13 矩阵上自动跑（推 main 或 PR 触发）。

---

## 参考文件

| 文件 | 作用 |
|---|---|
| `AGENTS.md` | Qoder AI 入口（包含 trellis-lite 指令块） |
| `.trellis-lite/workflow.md` | 3 阶段工作流详细说明 |
| `.trellis-lite/scripts/trellis.py` | 任务管理 CLI（唯一入口） |
| `.trellis-lite/spec/` | 编码规范（AI 写代码前必读） |
| `.trellis-lite/workspace/<dev>/journal-*.md` | 跨会话记忆 |
| `lite/docs/design.md` | 设计原理与架构文档 |
| `lite/tests/` | 161 个 unittest（回归保护） |
