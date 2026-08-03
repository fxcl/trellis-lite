# Trellis Lite

**Trellis 的精简版** — 为敏捷个人开发者打造的 AI 编码工作流框架。

## 为什么是 Lite？

原版 Trellis 功能强大但复杂：4 阶段工作流、20+ 平台适配、多 agent 协作（Channel）、跨会话记忆系统（Memory）、JSONL 上下文清单。对于个人开发者来说，这些往往用不上。

Trellis Lite 保留核心价值，砍掉所有非必要复杂度：

| 原版 Trellis | Trellis Lite |
|---|---|
| 20+ Python 脚本 | **1 个**单文件脚本（~835 行） |
| 4 阶段工作流 | **3 阶段**（PLAN → CODE → WRAP） |
| 20+ 平台适配 | **5 个**（Qoder、Claude Code、OpenCode、Cline + AGENTS.md 通用） |
| Channel 多 agent 协作 | 移除 |
| Memory 系统（SQLite） | 移除 |
| JSONL 上下文清单 | 移除（AI 直接读 PRD + spec） |
| Sub-agent 分发 | **保留**（通过 Qoder agent） |
| 外部依赖 | **零依赖**（仅需 Python 3.9+） |

## 快速开始

```bash
# 1. 安装到你的项目（默认支持所有平台）
cd /path/to/your/project
/path/to/lite/install.sh . yourname

# 1b. 或只安装特定平台
/path/to/lite/install.sh . yourname --platforms claude
/path/to/lite/install.sh . yourname --platforms qoder,cline

# 2. 在你的 AI 工具中打开项目（Qoder / Claude Code / OpenCode / Cline）
# AI 会自动读取对应入口文件，遵循工作流

# 3. 创建第一个任务
python3 .trellis-lite/scripts/trellis.py task create "实现用户登录"
```

### 支持的平台

| 平台 | 入口文件 | 安装参数 |
|---|---|---|
| Qoder | `AGENTS.md` | `--platforms qoder` |
| OpenCode | `AGENTS.md`（原生兼容） | `--platforms opencode` |
| Claude Code | `CLAUDE.md`（通过 `@AGENTS.md` 导入） | `--platforms claude` |
| Cline | `.clinerules/trellis-lite.md` | `--platforms cline` |
| 全部 | 以上所有 | `--platforms all`（默认） |

## 目录结构

安装后你的项目会包含：

```
your-project/
├── AGENTS.md                    # Qoder / OpenCode 入口
├── CLAUDE.md                    # Claude Code 入口（@import AGENTS.md）
├── .clinerules/
│   └── trellis-lite.md          # Cline 入口
└── .trellis-lite/
    ├── scripts/
    │   └── trellis.py           # 单文件任务管理器
    ├── workflow.md              # 3 阶段工作流定义
    ├── skills/                  # AI 行为指导
    │   ├── brainstorm.md        # 需求发现
    │   ├── before-dev.md        # 编码前加载 spec
    │   ├── check.md             # 质量验证
    │   └── update-spec.md       # 记录经验
    ├── spec/                    # 项目编码规范
    │   └── README.md            # 规范编写指南
    ├── tasks/                   # 活跃任务
    │   └── archive/             # 已归档任务
    ├── workspace/               # 开发者日志
    │   └── yourname/
    │       ├── index.md
    │       └── journal-1.md     # 会话记录
    ├── .developer               # 开发者身份
    └── .current-task             # 当前任务指针
```

## CLI 命令参考

```bash
# 初始化
python3 .trellis-lite/scripts/trellis.py init <name>

# 任务管理
python3 .trellis-lite/scripts/trellis.py task create "<title>" [--slug <name>]
python3 .trellis-lite/scripts/trellis.py task start <name>
python3 .trellis-lite/scripts/trellis.py task current
python3 .trellis-lite/scripts/trellis.py task finish
python3 .trellis-lite/scripts/trellis.py task archive <name>
python3 .trellis-lite/scripts/trellis.py task list

# 会话记录
python3 .trellis-lite/scripts/trellis.py session --title "..." --summary "..." [--commit <hash>]

# AI 上下文（AI 自动调用）
python3 .trellis-lite/scripts/trellis.py context
python3 .trellis-lite/scripts/trellis.py specs
```

## 工作流（3 阶段）

```
PLAN ────────────────► CODE ────────────────► WRAP
                       │
 triage task            load specs            update specs
 write PRD              implement             commit
 review & start         quality check         archive & record
```

详见 [`.trellis-lite/workflow.md`](.trellis-lite/workflow.md)。

## 与原版 Trellis 的关系

Trellis Lite 是 [Trellis](https://github.com/) 的独立子集，设计原则：

1. **一个脚本搞定一切** — 不拆分到多个文件
2. **零外部依赖** — 纯 Python 标准库
3. **文件即数据库** — 任务用 JSON，日志用 Markdown，不引入 SQLite
4. **AI 直接消费** — 去掉 JSONL 中间层，AI 直接读 PRD 和 spec 文件
5. **保留 Sub-agent** — 实现和检查可分发给专用 agent

适合 1 人团队 + AI 编码工具（Qoder / Claude Code / OpenCode / Cline）的开发场景。如果你的团队增长到多人协作，可以迁移到完整版 Trellis。
