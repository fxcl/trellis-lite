# Trellis Lite — 平台支持与实现逻辑

> 配套文档：[README.md](../README.md) · [usage-guide.md](usage-guide.md) · [design.md](design.md) · [best-practices.md](best-practices.md)

## 一、支持的平台总览

Trellis Lite 支持 4 个 AI 编码工具，核心工作流（PLAN → CODE → WRAP）和 `trellis.py` CLI 在所有平台**完全一致**，差异仅在**入口文件**和 **sub-agent 分发方式**。

| 平台 | 入口文件 | 原理 | 安装参数 |
|---|---|---|---|
| **Qoder** | `AGENTS.md` | 原生支持 AGENTS.md 标准 | `--platforms qoder` |
| **OpenCode** | `AGENTS.md`（与 Qoder 共享） | 原生兼容 AGENTS.md 标准 | `--platforms opencode` |
| **Claude Code** | `CLAUDE.md` | 通过 `@AGENTS.md` 导入语法桥接 | `--platforms claude` |
| **Cline** | `.clinerules/trellis-lite.md` | Cline 自动检测 `.clinerules/` 目录 | `--platforms cline` |
| **全部** | 以上所有 | — | `--platforms all`（默认） |

---

## 二、各平台实现逻辑

### 1. Qoder

- **入口文件**：`AGENTS.md`（完整指令，平台无关）
- **实现逻辑**：Qoder 原生读取 `AGENTS.md` 作为 AI 指令文件。内容包含：
  - 工作流文件指引（`.trellis-lite/workflow.md`）
  - 任务管理器命令（`trellis.py` 的 init / task / session / context / specs / doctor / version）
  - specs 约定（`.trellis-lite/spec/*.md`）
  - 3-phase 循环（PLAN → CODE → WRAP）
  - 规则（Plan before code / Read specs first / One task at a time / No auto-commit / Capture learnings / Be efficient）
  - Sub-Agent 用法（优先 trellis-brainstorm / trellis-implement / trellis-check）
- **Sub-Agent 机制**：`.qoder/agents/` 安装 3 个平台专用 agent（trellis-brainstorm / trellis-implement / trellis-check），通过 `Agent` 工具派发
- **Skills（slash 入口）**：`.qoder/skills/trellis-*/SKILL.md` 由 install.sh 在安装时生成，共 12 个 slash 入口：4 个深度流程 skill（trellis-brainstorm / trellis-before-dev / trellis-check / trellis-update-spec，正文源 `.trellis-lite/skills/*.md`）+ 8 个 py 命令映射（trellis-context / trellis-new / trellis-start / trellis-finish / trellis-archive / trellis-doctor / trellis-cancel / trellis-list，正文源 `templates/claude/commands/`，与 Claude/OpenCode 同源；`/trellis-check` 由深度流程版承担），三平台 slash 入口对等

### 2. OpenCode

- **入口文件**：`AGENTS.md`（与 Qoder **共享同一文件**）
- **实现逻辑**：OpenCode 原生兼容 AGENTS.md 标准，因此直接复用 Qoder 的入口文件，无需单独维护。install.sh 中 `has_platform "qoder" || has_platform "opencode"` 共用同一复制逻辑，但 `INSTALLED_PLATFORMS` 数组分别记录两个平台。
- **Sub-Agent 机制**：`.opencode/agents/` 安装 3 个平台专用 agent（与 Qoder 同名，frontmatter 遵循 OpenCode 规范：description / mode / permission）
- **Commands**：`.opencode/commands/` 安装 9 个命令（trellis-context … trellis-list），与 Claude Code 命令同源（正文零拷贝，仅去掉 `allowed-tools` frontmatter）

### 3. Claude Code

- **入口文件**：`CLAUDE.md`（桥接文件）
- **实现逻辑**：Claude Code 启动时静态读取 `CLAUDE.md`。该文件通过 `@AGENTS.md` 一行导入语法将完整指令桥接进来，**避免重复维护两份指令**。文件额外包含 Claude Code 平台特有内容：
  - **Sub-Agent 分发**：`Task` 工具，`subagent_type: "general-purpose"` 实现，`"code-reviewer"` 审查
  - **Slash 命令**：`.claude/commands/` 安装 9 个命令（`/trellis-context` / `/trellis-new` / `/trellis-start` / `/trellis-check` / `/trellis-finish` / `/trellis-archive` / `/trellis-doctor` / `/trellis-cancel` / `/trellis-list`，扁平 `trellis-*.md` 文件名，与 OpenCode 命名空间一致），包装 trellis.py 子命令
- **注意**：AGENTS.md 末尾注明 "Platform-specific sub-agent guidance is in the bridge file (e.g. CLAUDE.md for Claude Code)"，即平台特有内容放在桥接文件中，AGENTS.md 保持平台无关。

### 4. Cline

- **入口文件**：`.clinerules/trellis-lite.md`
- **实现逻辑**：Cline 自动检测 `.clinerules/` 目录下的规则文件。**关键差异**：Cline **不支持 `@import` 语法**，所以 install.sh 直接 `cp AGENTS.md` 复制完整内容到 `.clinerules/trellis-lite.md`（而非像 Claude Code 那样用 import 桥接）。
- **Sub-Agent 机制**：无原生 sub-agent，在主会话中直接实现，或通过 MCP 扩展
- **Skills（slash 入口）**：`.cline/skills/trellis-*/SKILL.md` 由 install.sh 在安装时生成，共 12 个 slash 入口，与 Qoder 同一生成循环产出（字节级一致）：4 个深度流程 skill（正文源 `.trellis-lite/skills/*.md`）+ 8 个 py 命令映射（正文源 `templates/claude/commands/`）。触发方式：`/skill-name` slash 命令显式触发，或 description 自动匹配（use_skill 工具）。Cline 无独立 agents 机制（单会话，主会话直接实现）

---

## 三、install.sh 安装逻辑（平台相关部分）

### 参数解析

```bash
./install.sh [target-dir] [developer-name] [--platforms <list>]
```

- `--platforms <list>` 或 `--platforms=<list>`，逗号分隔多平台
- 默认 `all`（安装全部平台）

### 平台校验

```bash
VALID_PLATFORMS=("qoder" "claude" "opencode" "cline" "all")
```

未知平台报错退出：`Error: unknown platform '$p'. Valid: qoder claude opencode cline all`

### has_platform() 判断函数

```bash
has_platform() {
    local p="$1"
    [[ "$PLATFORMS" = "all" || ",$PLATFORMS," = *",$p,"* ]]
}
```

### 安装映射

| 平台 | 源文件 | 目标文件 | 说明 |
|---|---|---|---|
| Qoder / OpenCode | `AGENTS.md` | `AGENTS.md` | 共用同一复制逻辑 |
| Qoder | `templates/qoder/agents/*.md` | `.qoder/agents/*.md` | 3 个平台专用 agent |
| Qoder | `.trellis-lite/skills/*.md` | `.qoder/skills/trellis-*/SKILL.md` | 安 装时生成 4 个深度流程 skill（薄 frontmatter + 原文） |
| Qoder | `templates/claude/commands/trellis-*.md` | `.qoder/skills/trellis-*/SKILL.md` | 安 装时生成 8 个 py 命令映射（与 Claude 版同源；check 由深度流程版承担） |
| Claude Code | `CLAUDE.md` | `CLAUDE.md` | 独立复制 |
| Claude Code | `templates/claude/commands/trellis-*.md` | `.claude/commands/trellis-*.md` | 9 个 slash 命令 |
| OpenCode | `templates/opencode/agents/*.md` | `.opencode/agents/*.md` | 3 个平台专用 agent |
| OpenCode | `templates/opencode/commands/*.md` | `.opencode/commands/*.md` | 9 个命令（与 Claude 版同源） |
| Cline | `AGENTS.md` | `.clinerules/trellis-lite.md` | `mkdir -p .clinerules/` + 复制完整内容 |
| Cline | `.trellis-lite/skills/*.md` | `.cline/skills/trellis-*/SKILL.md` | 安 装时生成 4 个深度流程 skill（与 Qoder 同一循环） |
| Cline | `templates/claude/commands/trellis-*.md` | `.cline/skills/trellis-*/SKILL.md` | 安 装时生成 8 个 py 命令映射（与 Qoder/Claude 版同源；check 由深度流程版承担） |

### 幂等保护

- 入口文件已存在则**跳过复制**（保留用户编辑过的版本），提示手动 merge
- `.trellis-lite/` 已存在则跳过复制，提示先 `rm -rf` 才能覆盖
- `.developer` 已存在则跳过 init（不覆盖用户刻意设置的开发者身份）

### F50 rollback 机制

- `INSTALLED_FILES` 数组跟踪所有写入的文件/目录
- `trap rollback ERR`：init 失败（Python 缺失 / 权限拒绝 / Python 3 < 3.9）时自动清理部分安装状态
- init 成功后 `trap - ERR` 关闭 rollback（后续 gitignore / hook 步骤失败不清理已成功部分）

---

## 四、各平台安装时创建的文件/文件夹

### 1. 所有平台共有（install.sh 无条件创建）

| 路径 | 来源 | 说明 |
|---|---|---|
| `.trellis-lite/` | 整个目录复制 | 运行时核心 |
| ├── `scripts/trellis.py` | 复制 | 单文件任务管理器 |
| ├── `workflow.md` | 复制 | 3 阶段工作流定义 |
| ├── `skills/` | 复制 | AI 行为指导（brainstorm / before-dev / check / update-spec） |
| ├── `spec/` | 复制 | 项目编码规范（README.md + TEMPLATE.md） |
| ├── `tasks/` + `tasks/archive/` | 复制 | 活跃任务 + 归档目录 |
| ├── `workspace/` | 复制 | 开发者会话日志 |
| └── `.developer` | init 生成 | 开发者身份（写入 .gitignore） |
| `.gitignore` | 追加 | `# Trellis Lite runtime` 块 + 2 条 runtime 条目 |
| `.git/hooks/pre-commit` | 复制（目标有 .git 时） | 提交前跑 `trellis doctor` |

### 2. 各平台特有的入口文件

| 平台 | 创建的文件/文件夹 | 说明 |
|---|---|---|
| **Qoder** | `AGENTS.md` + `.qoder/agents/`（3 个：brainstorm / implement / check） + `.qoder/skills/trellis-*/SKILL.md`（12 个，安装时生成：4 深度流程 + 8 py 命令映射） | 原生入口 + 平台专用 agents + slash 入口 |
| **OpenCode** | `AGENTS.md`（与 Qoder 共享） + `.opencode/agents/`（3 个） + `.opencode/commands/`（9 个：trellis-context … trellis-list） | 原生兼容 + 平台专用 agents + 命令 |
| **Claude Code** | `CLAUDE.md` + `.claude/commands/`（9 个：`/trellis-*` 命名空间） | `@AGENTS.md` 桥接 + slash 命令 |
| **Cline** | `.clinerules/` 目录 + `.clinerules/trellis-lite.md` + `.cline/skills/trellis-*/SKILL.md`（12 个，安装时生成：4 深度流程 + 8 py 命令映射） | 复制 AGENTS.md 完整内容 + skills slash 入口（无 agents 机制） |

### 3. 使用过程中动态创建（非安装时）

| 路径 | 触发命令 | 说明 |
|---|---|---|
| `.trellis-lite/.current-task` | `task start` | 当前任务指针 |
| `.trellis-lite/tasks/MM-DD-slug/`（task.json + prd.md） | `task create` | 任务目录 |
| `.trellis-lite/workspace/<dev>/journal-N.md` | `session` | 会话日志（每 2000 行自动轮转） |

---

## 五、Sub-Agent 差异对比

| 平台 | Sub-Agent 机制 | Trellis 专用 agents | 命令 |
|---|---|---|---|
| **Qoder** | `Agent` 工具派发 | `.qoder/agents/` 3 个（brainstorm / implement / check） | `.qoder/skills/` 12 个 slash 入口（4 深度流程 + 8 py 命令映射） |
| **Claude Code** | `Task` 工具派发（通用 `general-purpose` / `code-reviewer`） | — | `.claude/commands/` 9 个 `/trellis-*` |
| **OpenCode** | 内置 agent 系统 | `.opencode/agents/` 3 个（同名，OpenCode frontmatter） | `.opencode/commands/` 9 个 |
| **Cline** | 无原生 sub-agent | — | `.cline/skills/` 12 个 slash 入口（与 Qoder 同源生成；主会话直接实现） |

> 小/中等任务在所有平台都是主会话直接实现，sub-agent 仅影响大任务。三平台 agent 模板正文同源（差异仅在 frontmatter），正文单一源在 `templates/`，skills 正文单一源在 `.trellis-lite/skills/`。

---

## 六、核心结论

1. **核心工作流完全一致**：所有平台的 PLAN → CODE → WRAP 流程和 `trellis.py` CLI 完全相同，差异仅在入口文件和 sub-agent 分发方式。
2. **入口文件策略**：
   - Qoder / OpenCode → 原生 AGENTS.md（零桥接）
   - Claude Code → `@AGENTS.md` import 桥接（避免重复维护）
   - Cline → 复制完整内容（不支持 import 语法）
3. **Sub-agent 与命令分发**：Qoder（`.qoder/agents/` + `.qoder/skills/`）、Claude Code（`.claude/commands/` trellis-* 命令）、OpenCode（`.opencode/agents/` + `.opencode/commands/`）、Cline（`.cline/skills/` 12 个 slash 入口，无 agents 机制主会话直接实现）。agents/commands 正文单一源在 `templates/`，skills 正文单一源在 `.trellis-lite/skills/`（SKILL.md 包装首次安装时生成，重装不覆盖；源更新后删 `.qoder/skills/trellis-*/` 或 `.cline/skills/trellis-*/` 重装可重新生成）。
4. **安装幂等**：所有入口文件均受幂等保护，重装不会覆盖用户编辑过的版本。