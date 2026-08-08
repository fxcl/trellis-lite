# Trellis Lite — 任务开发 Checklist

> 每次开新任务，把对应阶段的清单复制到笔记里逐项打勾。
>
> 配套文档：[README.md](../README.md) · [installation-guide.md](installation-guide.md) · [usage-guide.md](usage-guide.md) · [trellis-cli.md](trellis-cli.md) · [best-practices.md](best-practices.md) · [design.md](design.md) · [platforms.md](platforms.md)

---

## 0. 一次性初始化（项目级）

只在新项目第一次安装时执行。

- [ ] **安装**：`./install.sh . <yourname> [--platforms qoder,claude,cline,opencode|all]`
- [ ] **验证入口文件**：至少 `AGENTS.md`（Qoder / OpenCode）
- [ ] **初始化开发者身份**：`python3 .trellis-lite/scripts/trellis.py init <yourname>`
- [ ] **校验 `.trellis-lite/.developer`** 文件存在
- [ ] **写前 3 个 spec**（按优先级）：
  - [ ] `spec/conventions.md` — 命名、缩进、错误格式
  - [ ] `spec/api-patterns.md` — 端点、响应结构、状态码
  - [ ] `spec/gotchas.md` — 已知坑位
- [ ] **跑一次 context** 验证：`python3 .trellis-lite/scripts/trellis.py context`

---

## 1. PLAN 阶段（任务开始前）

### 1.1 Triage（5 分钟法则）

- [ ] **判断任务规模**：
  - [ ] < 5 分钟 → 直接干，**跳过本流程**
  - [ ] 5–30 分钟 → 创建任务 + PRD-only
  - [ ] 30 分钟+ → 任务 + PRD + design notes
  - [ ] 跨多文件 → 任务 + 可能 sub-agent

### 1.2 创建任务

- [ ] **创建**：`task create "<title>" --slug <name>`
  - title 用 `动词 + 范围`（如 "实现用户登录"）
  - slug 用 `kebab-case`（如 `user-login`）
  - CJK 标题可省略 `--slug`，自动用 md5 hash
- [ ] **检查 `.current-task`** 是否指向新任务
- [ ] **如有活跃任务时新建**：会被拒绝（exit 1），先 finish/cancel 或用 `--replace` 显式接管

### 1.3 写 PRD

> **Read `.trellis-lite/skills/brainstorm.md` first** — 探索代码库后才问用户。

- [ ] **先探索代码**（brainstorm 原则：能搜就搜，别问用户）
- [ ] **PRD 4 必备部分**：
  - [ ] **Goal** — 一句话，陌生人能懂
  - [ ] **Requirements** — 动词 + 数字（不是名词）
  - [ ] **Acceptance Criteria** — 可验证（每条都 // 验证）
  - [ ] **Notes** — 不显然的约束
- [ ] **复杂任务**：加 `## Design` 段落或独立 `design.md`（模块边界、数据流、权衡）

### 1.4 审 PRD 与启动

- [ ] **给用户看 PRD**（AI 不会自动 start）
- [ ] **用户确认** → `task start <name>`
- [ ] **检查状态**：status → `in_progress`
- [ ] **如有其他 in_progress 任务**：会有 Warning

---

## 2. CODE 阶段（实现中）

> **Read `.trellis-lite/skills/before-dev.md` first** — 写代码前必读。

### 2.1 加载上下文

- [ ] **读 prd.md** 全文
- [ ] **跑 specs**：`python3 .trellis-lite/scripts/trellis.py specs`
- [ ] **读相关 spec**：`cat .trellis-lite/spec/<relevant>.md`
- [ ] **读同目录现有代码**：理解命名、错误处理、import 风格

### 2.2 实现

**直接实现**（小/中等任务）：
- [ ] 写代码
- [ ] 跑项目 lint/typecheck/test

**Sub-agent 分发**（大任务）：
- [ ] **Prompt 必须以 `Active task: <path>` 开头**
- [ ] 分发 `GeneralPurpose`（实现）
- [ ] 等报告
- [ ] 主 AI 合并改动

### 2.3 质量检查

> **Read `.trellis-lite/skills/check.md` first** — 完整检查流程。

- [ ] **git status --porcelain** 看改了哪些
- [ ] **逐项核 Acceptance Criteria**
- [ ] **自测**（小任务）：跑 lint + typecheck + test
- [ ] **CodeReview agent**（大任务）：prompt 同上格式，检查 diff
- [ ] **修复机械问题**（lint/type 错）
- [ ] **不要静默改设计问题**：报告，不改

### 2.4 检查报告

完成后输出：
```
## Check Complete
### Files Reviewed
- <path>

### Issues Fixed
1. `<file>:<line>` — <what> → <fix>

### Issues Open
- `<file>:<line>` — <issue> — <why deferred>

### Verification
- Lint: pass/fail
- TypeCheck: pass/fail
- Tests: pass/fail
```

---

## 3. WRAP 阶段（任务收尾）

### 3.1 更新 Spec（如有）

> **Read `.trellis-lite/skills/update-spec.md` first** — 怎么写 spec。

- [ ] **是否学到新东西？**
  - [ ] 调试过的坑 → 写 gotcha 到对应 spec
  - [ ] 新约定的模式 → 写 rule 到 conventions.md
  - [ ] 发现的 API 契约 → 写到 api-patterns.md
- [ ] **格式**：可执行合同（不是模糊原则）
- [ ] **写完后**：git add + commit（与代码改动一同或单独）

### 3.2 Finish

- [ ] **task finish**（状态 → done，清除 .current-task）
- [ ] **如有 dirty 工作树**：会有 Warning，先 commit 或 stash

### 3.3 Commit

> **AI 永远不自动 commit。必须先问用户。**

- [ ] **问用户**："可以 commit 吗？"
- [ ] **用户确认后**：
  - [ ] `git status --porcelain`
  - [ ] `git log --oneline -5`（学 commit 风格）
  - [ ] `git add <files>`（按逻辑分组）
  - [ ] `git commit -m "<conventional-commit: feat|fix|chore|...>"`

### 3.4 Archive

- [ ] **task archive <name>** → 移动到 `tasks/archive/YYYY-MM/`
- [ ] **任务目录**：包含 prd.md、可选 design.md
- [ ] **.current-task 自动清除**

### 3.5 记录 Session

- [ ] **session**：
  ```bash
  python3 .trellis-lite/scripts/trellis.py session \
      --title "<动词 + 范围>" \
      --summary "<做了什么 + 关键决定 + 已知遗留>" \
      --commit <hash>
  ```
- [ ] **Title 规则**：动词 + 范围（一行能扫）
- [ ] **Summary 规则**：做了什么 / 关键决定 / 已知遗留
- [ ] **Commit 必须是 4–64 位 hex**（4–40 SHA-1 / 64 SHA-256；git 2.42+ 默认为 SHA-256。非 hex 会被拒绝（exit 1））

### 3.6 异常流程

- [ ] **任务放弃（不做）**：`task cancel <name>`（状态 → cancelled，**保留目录**）
- [ ] **scope 变更**：更新 PRD → 重新确认 → 继续
- [ ] **临时切换任务**：`task finish` 当前 → 再 `task start` 新任务

---

## 4. 跨会话恢复

> 隔了几天/几周回来："接着做上次那个"

- [ ] **唤醒项目**：`python3 .trellis-lite/scripts/trellis.py context`
- [ ] **看 Last session 行**：知道上次在哪
- [ ] **看 Active task**：知道当前 in_progress
- [ ] **task current**：看 title + status + artifacts
- [ ] **读 prd.md**：回忆 Goal + Acceptance
- [ ] **git log --oneline -10**：看上次 commit
- [ ] **继续实现剩余 acceptance**

**5 步全部 read-only，不会意外改动代码**。

---

## 5. 用户视角速查

| 你想做的 | AI 自动做的事 |
|---|---|
| "我做 X" | triage → task create → PRD 给你看 |
| "X 任务开干" | task start → 读 spec → 写代码 |
| "X 怎么样了" | task current + diff report |
| "X 收尾" | task finish → commit 问 → archive → session |
| "接着上次" | context → task current → 读 PRD → 继续 |
| "看上次 e2e" | task list --all → 找 → 读 journal + PRD |
| "这个不要了" | task cancel <name> |
| "项目规范是啥" | specs |

---

## 6. AI 视角必读清单

每个新 session 开始：

- [ ] 读 `task current`（如有 in_progress）
- [ ] 读 `prd.md`（当前任务）
- [ ] 跑 `specs` 找相关 spec
- [ ] 读相关 spec
- [ ] 读同目录现有代码

每次发现新东西：

- [ ] 写 spec（可执行合同）
- [ ] 写 session（做了什么）

**绝不**：

- [ ] 自动 commit（必须先问用户）
- [ ] 跳过 PRD 就 start
- [ ] 跳过 spec 就写代码
- [ ] 静默改设计问题
- [ ] 并行跑多个 trellis 命令（`.current-task` 不线程安全）

---

## 7. Copy-paste 模板

### 7.1 新任务模板（复制到任务笔记）

```markdown
# <任务标题>

## PLAN
- [ ] Triage：5min 法则
- [ ] task create "<title>" --slug <name>
- [ ] 写 PRD：Goal / Requirements / Acceptance / Notes
- [ ] 用户确认 → task start <name>

## CODE
- [ ] 读 PRD
- [ ] 跑 specs 找相关 spec
- [ ] 实现
- [ ] 跑 lint/typecheck/test
- [ ] CodeReview (大任务)

## WRAP
- [ ] 更新 spec（如有新发现）
- [ ] task finish
- [ ] 问用户 → git commit
- [ ] task archive
- [ ] session --title --summary --commit

## 备注
- <不显然的约束>
- <可复用资源>
```

### 7.2 跨会话恢复模板

```markdown
# 恢复自 <日期>

## 上次在哪
- 任务：<name>
- 状态：<status>
- Last session 标题：<title>

## 接着做
- [ ] <acceptance criterion 1>
- [ ] <acceptance criterion 2>
```

---

## 8. 规则速查

| # | 规则 | 出处 |
|---|---|---|
| 1 | < 5 分钟直接干 | workflow.md |
| 2 | PRD 是契约，更新它当需求变 | workflow.md |
| 3 | Spec 为"将来会忘的事"写 | workflow.md |
| 4 | 1 个时间 1 个 in_progress | workflow.md |
| 5 | Journal 廉价，记录每个有意义的 session | workflow.md |
| 6 | **不要并行跑 trellis 命令** | workflow.md |
| 7 | AI 永不自动 commit（先问用户） | workflow.md, AGENTS.md |
| 8 | Spec 是可执行合同，不是模糊原则 | update-spec.md |
| 9 | 发现坑 → 写 spec 防再发生 | update-spec.md |
| 10 | session title 动词 + 范围 | session 模板 |
