# Trellis Lite — 安装手顺

> 配套文档：[README.md](../README.md) · [usage-guide.md](usage-guide.md) · [platforms.md](platforms.md) · [design.md](design.md)

> 本文档是 Trellis Lite 的**完整安装操作手册**：从前置条件到安装、验证、故障排查、卸载，覆盖全过程。
>
> 简明版见 [README「快速开始」](../README.md)；平台细节见 [platforms.md](platforms.md)。

---

## 一、前置条件

| 依赖 | 版本要求 | 说明 |
|---|---|---|
| **bash** | 4.0+ | install.sh / uninstall.sh 使用 `read -ra` 与 `arr+=()` 语法，bash 3.2 不支持 |
| **Python** | 3.9+ | `trellis.py` 运行时（纯标准库，零外部依赖） |
| **git** | 可选 | 存在 `.git/` 时才安装 pre-commit hook |

### macOS 前置检查

macOS 默认 `/bin/bash` 是 **3.2.57**（最后 GPLv2 版本），不满足要求。需通过 Homebrew 安装：

```bash
# 安装 bash 4+
brew install bash

# 用新 bash 运行安装
/usr/local/bin/bash install.sh . <name>
```

检查当前 bash 版本：

```bash
bash --version
```

Linux 用户通常自带 bash 4+（位于 `/usr/bin/bash`），一般无需处理。

### Python 检查

```bash
python3 --version   # 需 ≥ 3.9
```

---

## 二、安装手顺（分步操作）

### Step 1：获取 Trellis Lite

方式一：克隆本仓库

```bash
git clone https://github.com/fxcl/trellis-lite.git
cd trellis-lite/lite
```

方式二：使用已有副本（直接定位到含 `install.sh` 的目录）。

### Step 2：确定目标项目目录

Trellis Lite 会安装到**你的业务项目根目录**（不是本仓库）。确认目标目录存在：

```bash
ls -d /path/to/your/project
```

### Step 3：选择平台

Trellis Lite 支持 4 个 AI 编码工具，安装时按需选择：

| 平台 | 入口文件 | 安装参数 |
|---|---|---|
| Qoder | `AGENTS.md` | `--platforms qoder` |
| OpenCode | `AGENTS.md` | `--platforms opencode` |
| Claude Code | `CLAUDE.md` | `--platforms claude` |
| Cline | `.clinerules/trellis-lite.md` | `--platforms cline` |
| **全部** | 以上所有 | `--platforms all`（**默认**） |

不确定时直接使用默认 `all`，安装全部平台入口，后续哪个工具打开都能识别。

### Step 4：执行安装

在**本仓库目录**（含 `install.sh`）执行：

```bash
# 全部平台（默认，推荐）
./install.sh /path/to/your/project yourname

# 仅 Claude Code
./install.sh /path/to/your/project yourname --platforms claude

# 多平台（Qoder + Cline）
./install.sh /path/to/your/project yourname --platforms qoder,cline

# 可省略目标目录（默认安装到当前目录）与开发者名（默认 whoami）
./install.sh
```

安装成功输出：

```
✓ Trellis Lite installed!
Supported platforms: Qoder OpenCode Claude Code Cline
```

### Step 5：验证安装

检查入口文件是否生成：

```bash
# 在目标项目目录执行
ls -la AGENTS.md CLAUDE.md .clinerules/trellis-lite.md 2>/dev/null
ls -la .trellis-lite/
```

运行 doctor 自检（9 项健康检查）：

```bash
python3 .trellis-lite/scripts/trellis.py doctor
```

- 全部通过：`✓` 状态，即可使用
- 有问题：运行 `--fix` 自动修复，或参考「五、故障排查」

### Step 6：在 AI 工具中打开项目

在 Qoder / Claude Code / OpenCode / Cline 中打开**目标项目目录**。

> ⚠️ **重要**：大多数 AI 工具在**会话启动时静态读取入口文件一次**，不支持热重载。安装后必须**新开一个会话**，AI 才能读到 Trellis Lite 指令。

验证 AI 是否加载成功：在新会话中问 AI「你读到了哪些指令文件？」，应能识别出 Trellis Lite 指令。

### Step 7：安装后收尾（可选但推荐）

```bash
# 1. 添加编码规范到 spec/
#    将你的项目约定写入 .trellis-lite/spec/*.md（模板见 spec/TEMPLATE.md）

# 2. 创建第一个任务
python3 .trellis-lite/scripts/trellis.py task create "我的第一个任务"
```

---

## 三、各平台安装对照表

| 场景 | 推荐参数 | 说明 |
|---|---|---|
| 新项目，从零开始 | `--platforms all`（默认） | 全部入口，未来哪个 AI 工具都能用 |
| 只用 Qoder | `--platforms qoder` | 个人 + Qoder 最简场景 |
| Qoder + Claude Code 跨设备 | `--platforms qoder,claude` | 不同设备用不同工具 |
| CI / 无头环境 | `--platforms opencode` | 最轻量，AGENTS.md 原生兼容 |
| VS Code 老用户 | `--platforms qoder,cline` | Cline 是 VS Code 插件 |

### 安装参数速查

```bash
./install.sh [target-dir] [developer-name] [--platforms <list>]
```

- `target-dir`：目标项目目录（默认 `.`）
- `developer-name`：开发者身份（默认 `whoami`）
- `--platforms <list>`：逗号分隔平台列表（默认 `all`）
- 也支持 `--platforms=<list>` 形式

---

## 四、重装语义（幂等性）

重复运行 install.sh **不会覆盖**：

| 已有内容 | 行为 | 提示 |
|---|---|---|
| `.trellis-lite/` | 跳过复制 | `⚠ .trellis-lite/ already exists. Skipping copy.` |
| `AGENTS.md` / `CLAUDE.md` | 跳过复制 | `⚠ already exists. Skipping (merge manually if needed).` |
| `.clinerules/trellis-lite.md` | 跳过复制 | `⚠ already exists. Skipping.` |
| `.developer` | 跳过 init | `Note: .developer already set to '...'; skipping init` |
| `.gitignore` runtime 条目 | 跳过添加 | grep 检测已存在则不重复追加 |
| `pre-commit` hook | 跳过安装 | `⚠ .git/hooks/pre-commit already exists. Skipping.` |

**想强制重装**：先删除已有安装再运行：

```bash
rm -rf .trellis-lite AGENTS.md CLAUDE.md .clinerules
./install.sh . yourname
```

> `.developer` 不覆盖是**有意设计**：用户可能刻意设置了开发者身份，重装不应静默改写。需要改名字时显式运行 `trellis.py init <newname>`。

---

## 五、故障排查

| 错误 | 原因 | 解决 |
|---|---|---|
| `Error: bash 4.0+ required` | bash 版本过低（macOS 默认 3.2） | `brew install bash`，用 `/usr/local/bin/bash install.sh ...` 重跑 |
| `Error: target directory not found` | 目标目录不存在 | 先创建目录或检查路径拼写 |
| `Error: unknown platform 'xxx'` | 平台名写错 | 合法值：`qoder` / `claude` / `opencode` / `cline` / `all` |
| init 阶段失败（Python 缺失 / 权限拒绝 / Python < 3.9） | 环境不满足 | 按错误提示修复后**重跑** install.sh（F50 rollback 已自动清理部分安装状态） |
| AI 读不到 Trellis Lite 指令 | 会话在安装前已打开 | **新开一个会话**（入口文件静态读取，不支持热重载） |
| `python3` 未找到 | Python 未安装 | 安装 Python 3.9+ |
| 无 `.git/` 目录 | pre-commit hook 未安装 | 业务项目 `git init` 后，手动复制 `lite/hooks/pre-commit` 到 `.git/hooks/pre-commit` |

> **F50 rollback 机制**：install.sh 跟踪所有写入的文件（`INSTALLED_FILES` 数组）。如果 init 阶段失败，`trap rollback ERR` 自动删除已复制的 `.trellis-lite/`、入口文件等，避免留下 broken state。重跑不会卡在「已复制但未初始化」的中间状态。

---

## 六、卸载手顺

```bash
# 在目标项目目录执行（省略参数默认当前目录）
./uninstall.sh .
```

卸载内容清单：

| 内容 | 说明 |
|---|---|
| `.trellis-lite/` | 整个运行时目录（含归档任务 `tasks/archive/YYYY-MM/`） |
| `AGENTS.md` / `CLAUDE.md` | 平台入口文件 |
| `.clinerules/trellis-lite.md` | Cline 规则文件（仅删 trellis-lite.md，保留用户其他规则；空目录自动清理） |
| `.gitignore` 中 `# Trellis Lite runtime` 块 | 仅删 Trellis 管理的 runtime 条目 |
| `.git/hooks/pre-commit` | 仅当内容是 Trellis Lite hook 时删除 |

**保护机制**：uninstall.sh 会先检查目标是否安装过 Trellis Lite（检测 `.trellis-lite/` / `AGENTS.md` / `CLAUDE.md` / `.clinerules/` 任一存在），否则拒绝执行，避免误删非 Trellis 项目。

> ⚠️ 卸载会删除归档任务。如有需要请先备份 `.trellis-lite/tasks/archive/`。

---

## 七、附录：安装后目录结构

```
your-project/
├── AGENTS.md                    # Qoder / OpenCode 入口
├── CLAUDE.md                    # Claude Code 入口（@import AGENTS.md）
├── .clinerules/
│   └── trellis-lite.md          # Cline 入口
├── .gitignore                   # 追加 Trellis Lite runtime 块
├── .git/hooks/pre-commit        # 提交前跑 trellis doctor（有 .git 时）
└── .trellis-lite/
    ├── scripts/
    │   └── trellis.py           # 单文件任务管理器
    ├── workflow.md              # 3 阶段工作流定义
    ├── skills/                  # AI 行为指导（4 个 markdown）
    ├── spec/                    # 项目编码规范
    │   ├── README.md
    │   └── TEMPLATE.md
    ├── tasks/                   # 活跃任务
    │   └── archive/             # 已归档任务
    ├── workspace/               # 开发者会话日志
    └── .developer               # 开发者身份（install 生成，gitignore）
```

> `.current-task` 是 `task start` 时动态创建，不在安装时生成。