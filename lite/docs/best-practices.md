# Trellis Lite — 最佳实践指南

> 基于 13 轮 oracle-reviewer 审查沉淀 + ~1857 行实现 + 165 个 unittest 覆盖的实战经验。
>
> 配套文档：
> - [README.md](../README.md) — 快速上手
> - [design.md](design.md) — 设计原理与架构
> - [usage-guide.md](usage-guide.md) — 完整使用示例
> - [workflow-checklist.md](workflow-checklist.md) — 任务级 checklist（可复制）
> - [exit-codes.md](exit-codes.md) — 退出码语义与可逆性原则
> - [architecture-review.md](architecture-review.md) — 架构审查记录与债务清单
> - [workflow.md](../.trellis-lite/workflow.md) — AI 行为规范

---

## 序：为什么需要"最佳实践"

Trellis Lite 是一个**协议**：它不强制你做任何事，但告诉你哪些方式更高效。

照做的好处：
- 跨会话恢复：5 分钟 vs 30 分钟
- AI 写规范代码：90%+ vs 30%
- 项目历史可追溯：可问 vs 不可问
- 多任务不混乱：有序 vs 混乱

不照做也能跑，但你会逐渐偏离设计意图。

---

## 一、安装策略

### 推荐组合

| 场景 | 推荐装 |
|---|---|
| **新项目，从零开始** | `--platforms all`（默认） |
| **只用 Qoder** | `--platforms qoder` |
| **Qoder + Claude Code 跨设备** | `--platforms qoder,claude` |
| **CI / 无头环境** | `--platforms opencode`（最轻） |
| **VS Code 老用户** | `--platforms qoder,cline` |

### 安装后立刻验证

```bash
# 1. 装的入口文件对吗
cat .trellis-lite/.developer                # 应显示 name=yourname
ls .trellis-lite/spec/                      # 应有 README.md
cat .trellis-lite/workspace/yourname/journal-1.md  # 应有 # Journal 1

# 2. 跑一次 context 看输出
python3 .trellis-lite/scripts/trellis.py context

# 3. 跑 doctor 全面自检（详见第八节）
python3 .trellis-lite/scripts/trellis.py doctor
```

### 重装语义（O16）

`install.sh` 是**幂等**的。重复运行到同一目录不会覆写已有状态：

| 已有工件 | 重装行为 |
|---|---|
| `.trellis-lite/` 目录 | **跳过 cp**（使用现有；不会同步新模板） |
| `.trellis-lite/.developer` | **跳过 init**（输出 `Note: .developer already set to '...'`） |
| `AGENTS.md` / `CLAUDE.md` / `.clinerules/trellis-lite.md` | **跳过 cp**（保留用户编辑过的版本） |
| `.gitignore` runtime 条目 | **跳过添加**（grep 检测已存在） |
| `.git/hooks/pre-commit` | **跳过 cp**（保留旧 hook） |

**结论**：install 只在"目标未安装"时执行初始化动作。需要重新 init、改 dev name、刷新模板、迁移到新版本时，先 `uninstall.sh .` 再 `install.sh . <name>` —— **不要期望重装会"修复"任何东西**。

如果只是想检查健康状态：`doctor [--fix]`（详见第八节）。

---

## 二、任务分流：5 分钟法则

### 决策树

```
< 5 分钟    → 直接干，跳过任务系统
5-30 分钟   → 创建任务，只写 PRD
30 分钟+    → 创建任务 + PRD + design notes
跨多文件    → 必须任务 + 可能分 sub-agent
```

### 实战判断

| 场景 | 动作 | 理由 |
|---|---|---|
| 改一行 typo | 直接 `Edit` | 5 秒 |
| 改一个函数名（全仓库） | 直接 `Edit` | 1-2 分钟 |
| 加一个 helper 函数 | 创建任务 | 5-15 分钟 |
| 加一个 API 端点 | 创建任务 + PRD | 30 分钟 |
| 重构认证模块 | 任务 + PRD + design + sub-agent | 几小时 |
| 升级依赖大版本 | 任务 + 详细 PRD | 升级风险大 |

**核心原则**：**写未来 6 个月的你回看也会需要的 PRD**。

---

## 三、PRD 编写：决定 AI 输出质量的 80%

### 优秀 PRD 的 4 个特征

#### 1. Goal 一句话要锋利

```markdown
# 差
"加一个用户登录功能"

# 好
"实现邮箱密码登录，30 分钟内自动锁定，连续 5 次错误"
```

**判断标准**：陌生人读到 Goal 就能知道做完后会是什么样。

#### 2. Requirements 用动词

```markdown
# 差
"- 用户系统"
"- 安全"

# 好
"- 接受 POST /api/login with { email, password }"
"- 返回 JWT (HS256, 24h 过期) 在 Authorization header"
"- 5 次错误后锁定账号 30 分钟"
```

#### 3. Acceptance Criteria 必须可验证

```markdown
# 差（不可验证）
"- [ ] 登录能用"

# 好（可验证）
"- [ ] 错误密码第 6 次返回 429 with `Retry-After: 1800`
- [ ] 正确密码返回 200 + JWT
- [ ] JWT 24h 后过期，无刷新机制"
```

未来 `task check` 阶段 AI 将一条一条对。

#### 4. Notes 写不显然的约束

```markdown
## Notes
- 不能用 bcrypt 用 argon2id（合规要求 GDPR 第 32 条）
- 用户表已存在 users，使用现有 password_hash 字段
- 不做刷新 token，只做 24h 短期
- UI 已经有 `<LoginForm>` 组件，直接复用
```

### PRD 模板

```markdown
# <Title>

## Goal
<一句话，能让陌生人明确知道做完是什么样>

## Requirements
- <动词 + 对象 + 数字>
- <动词 + 对象 + 数字>

## Acceptance Criteria
- [ ] <可验证>
- [ ] <可验证>

## Notes
- <不显然的约束>
- <已存在的可复用资源>
- <明确排除的边界>
```

---

## 四、Spec 编写：让 AI 永不重复同样的错

### 何时该写 spec

**每当你调试了一个不在字面代码里能看出的问题**——写 spec。

```markdown
# 真实场景
"为什么我的 SQL 总是 N+1？"
→ 看了 10 分钟代码 → 发现没用 JOIN
→ 写 spec: "数据库查询必须用 JOIN 或 explode-in，禁止逐条查询"
→ 下次 AI 直接看 spec 就知道
```

### 4 大类别

| 类别 | 示例文件 | 解决什么 |
|---|---|---|
| **约定** | `conventions.md` | 命名、缩进、错误格式 |
| **API 模式** | `api-patterns.md` | 端点命名、响应结构、状态码 |
| **测试** | `testing.md` | mock 策略、覆盖率门槛、命名 |
| **踩坑** | `gotchas.md` | 每次调试的"线索" |

### Spec 模板

```markdown
# <Area> Spec

## Rule: <短名>
<一句话描述>

**Do:**
```typescript
// 正确示例
const users = await db.join('users', 'orders', 'users.id', 'orders.user_id')
  .where('orders.created_at', '>', weekAgo)
```

**Don't:**
```typescript
// 错误示例
for (const user of users) {
  user.orders = await db.query('SELECT * FROM orders WHERE user_id = ?', [user.id])
}
```

**Why:** 触发 N+1 查询，1000 用户 = 1001 次数据库调用。
```

### 写法对比

```markdown
# 差（模糊原则）
"优雅地处理错误"

# 好（可执行合同）
"所有公共函数 throw，错误对象包含 `code`、`message`、`context` 字段。
HTTP 状态码：4xx 客户端错误，5xx 服务端错误。
4xx 必须带 `Retry-After` header（限流时）。"
```

> **核心原则**：spec 是**可执行合同**，不是**模糊原则**。

### 写入流程

1. 识别你学到了什么（pattern / pitfall / contract）
2. `python3 .trellis-lite/scripts/trellis.py specs` 检查已有
3. 决定归属（已有文件 or 新建）
4. 写规则 + 正反例 + 为什么
5. **验证规则适用现有代码**（不仅当前改动）
6. 与代码一起 commit

---

## 五、Session 记录：把每一份知识沉淀

### 何时记

**每个完成的任务 + 任务**。超过 2000 行自动轮转。

### 模板

```bash
python3 .trellis-lite/scripts/trellis.py session \
    --title "实现登录 + 对接登录页 UI" \
    --summary "POST /api/login + JWT 签发 + 表单联动。5 次错误锁定 30 分钟用 Redis。bcrypt 用 argon2id 替代。" \
    --commit abc1234
```

### 标题（Title）规则

- 用动词 + 范围
- "实现" / "重构" / "修复" / "调研" / "升级"
- 一行能扫到

### 摘要（Summary）规则

- 写**做了什么**（不是研究了什么）
- 写**关键决定**（为什么选 A 不选 B）
- 写**已知遗留**（留给下次会话）

### 反例

```bash
# 太虚
-title "完成登录功能" -summary "完成了"

# 太流水账
-title "实现登录" -summary "先读了文件然后改了然后测了"
```

---

## 六、状态机与生命周期（必读）

任务状态机是 Lite 最容易踩坑的部分，因为它不仅是"状态转换"，还有**幂等性、时间戳、活跃指针**三重语义。

### 6.1 5 态状态机

```
planning ──(task start)──→ in_progress ──(task finish)──→ done ──(task archive)──→ archived
     │                         │                                                    │
     │                         │                                                    │
     └─────────────────────────┴───────────────── 也可以直接 archive（跳过 finish）──┘

planning / in_progress ──(task cancel)──→ cancelled（目录保留，不归档）
done ──(task cancel)──→ cancelled（允许“改主意”，是设计上唯一允许的反向转移）
```

完整转换表（来源：`trellis.py` 中的 `ALLOWED_TRANSITIONS` 常量）：

| 起始状态 | 允许转移目标 |
|---|---|
| `planning` | `in_progress`, `done`, `archived`, `cancelled` |
| `in_progress` | `done`, `archived`, `cancelled` |
| `done` | `archived`, `cancelled` |
| `archived` | （终态） |
| `cancelled` | （终态） |

**关键约束**：
- **Forward-only**：除了 `done → cancelled` 这一你“改主意”场景，不能回滚
- **终端状态不可转移**：`archived` 和 `cancelled` 是永久状态
- **跨期转移会被拒绝**：调用 `set_status()` 返回 `False` + 输出 Warning

### 6.2 set_status 幂等性

`set_status(task_dir, new_status)` 遵循幂等原则：

- **同一状态重复调用** → 返回 `True`，**不重写文件、不更新时间戳**
- **合法转移** → 返回 `True`，更新时间戳
- **非法转移 / 缺失文件 / 损坏 JSON / 空数据** → 返回 `False`，**不写任何东西**

这意味着以下脚本是安全的：

```bash
# 在 CI / hook 里重复调用不会产生副作用
python3 trellis.py task start my-task     # 首次：transfer planning → in_progress
python3 trellis.py task start my-task     # 幂等：返回 True，不重写 started 时间戳
```

### 6.3 时间戳约定（不要手动改 task.json）

`task.json` 中的时间戳对应**触发该状态转移的事件**：

| 字段 | 何时写入 | 何时不存在是正确 |
|---|---|---|
| `created` | `_task_create`（永不变） | — |
| `started` | 首次 `task start` | `planning` 任务**不有**（未开始，不是漏字段） |
| `finished` | `task finish` | `planning` / `in_progress` / `cancelled` 任务**不有** |
| `archived` | `task archive` | 仅 `archived` 任务上有 |
| `cancelled` | `task cancel` | 仅 `cancelled` 任务上有 |

> 判断“task.json 是否被人手动改过”的最快方法：看 `started` 是否在 `planning` 上存在。如果有，则可能被人工改了 —— 需人工判断（doctor 目前不检查时间戳合法性，P3-G 第 10 轮修正此承诺）。

### 6.4 One Task at a Time

`task create` 遵循硬规则：

```bash
# 如果已有活跃任务，create 默认拒绝 + exit 1（不创建文件夹）
$ python3 trellis.py task create "新功能"
Refusing to create: '08-04-login' is still the active task. Run 'task finish' or 'task cancel' first, or pass --replace to take over.

# 显式接管（旧任务自动置为 done，含 finished 时间戳，F49）：
$ python3 trellis.py task create "新功能" --replace
Note: replaced active task '08-04-login' with '08-04-new-feature'.
```

**反面**：多个 `in_progress` 并存会导致 `task finish` 只清一个活跃指针，其他任务“丢了但看不到”。**限制是你必须明确主动。**

### 6.5 任务生命周期决策树

```
任务结束 ?
├─ 完成了 → task finish（状态 done） → task archive（进 archive/YYYY-MM/）
│                                              └─ 写 session journal
├─ 不想做了 → task cancel <name>（状态 cancelled，目录保留）
│               └─ 写 session journal（说明为什么取消）
└─ 目录没用了 → task cancel + task delete --force（永久删除）

需要清理磁盘：
└─ task list --all 查看所有（含 archived）
└─ 手动 rm -rf tasks/archive/YYYY-MM/<name>（已 archived 的任务是可丢弃的）
```

### 6.6 清理路径（task delete）

`task delete <name> [--force]` 是 0.6.9 新增的“硬删除”命令：

- 默认只允许删除 `cancelled` 状态（防止误删仍在运行的）
- `--force` 跳过状态检查
- 删除前会清除 `.current-task` 指针（如果指向该任务）
- **不可逆** —— deleted 后无法恢复，但 session journal 中仍记录了 commit hash 可追溯

---

## 七、退出码语义（可逆性原则）

Lite 的退出码遵循一条原则：**不可逆操作失败必须中止（return 1）；可恢复操作失败可以降级继续（return 0 + Warning）**。

完整退出码表详见 [exit-codes.md](exit-codes.md)。以下是各 mutating 命令的副作用风险细节：

### 7.1 mutating 命令对损坏元数据一律拒绝（对称严格模式）

| 命令 | task.json 损坏时行为 | 返回码 | 原理 |
|---|---|---|---|
| `task finish` | **拒绝、活跃指针不变** | 1 | 副作用：调 `clear_current_task()` 清空指针——指针丢失不可逆 |
| `task start` | **拒绝、活跃指针不变** | 1 | 副作用：调 `set_current_task()` 切换指针。corrupted 后切换 → 后续 finish/cancel 看不到元数据（split-brain） |
| `task archive` | **拒绝、不移动目录** | 1 | 副作用：`shutil.move` 到 `archive/YYYY-MM/`。corrupted 后移动 → orphan（task list 看到 `[?]`） |
| `task cancel` | **拒绝、活跃指针不变** | 1 | 副作用：清理活跃指针。corrupted 后清理 → split-brain（指针已清但 task.json 不可读） |

**统一原则**：任何**会修改活跃指针或目录位置**的 mutating task 命令，遇到 `task.json` 缺失或损坏一律拒绝 + 返回 1，避免 split-brain。修复路径：`trellis.py doctor --fix`（推荐）/ `task delete --force <name>`（最后手段）。

**使用示例**：

```bash
# 安全管道：finish 失败明确中止脚本
set -e
python3 trellis.py task finish || { echo "active task missing — abort"; exit 1; }

# start 幂等：对已激活任务重复调用输出 Note + 返 0（安全无副作用）
python3 trellis.py task start my-task   # 即使重复调用也安全
```

### 7.2 查询类命令总是返 0

`task list` / `task current` / `specs` / `context` 在“空状态”时返 0：

```bash
# 无任务不是错误 —— 与 git/ls/find 一致
if python3 trellis.py task list | grep -q "$NAME"; then
    echo "task exists"
fi
```

**不要**把这些命令作为 CI 闸门用 —— 如果需要"有任务才跑"，用输出内容判断而非退出码。

---

## 八、doctor 自检与自愈

`doctor [--fix]` 是 Lite 的“体检 + 治疗”工具。**项目状态不正常时第一个该跑的命令**。

### 8.1 9 项检查

```
1. .trellis-lite/ 存在？否则 doctor 早退
2. .developer 文件存在且含 name=... 行（两种损坏形态：文件缺失 → Problem；无 name= 行 → Warning，--fix 均可恢复）
3. tasks/, tasks/archive/, spec/ 三个子目录都存在
4. workspace/<dev>/ 存在 + 至少 1 个 journal-N.md
5. .current-task 指针指向的目录存在，且其 task.json 可读（F55：corrupted 报 Problem ✗，驱动 exit 1；第 10 轮 P3-A：指向终态任务报 Warning ⚠）
6. tasks/*/ 与 tasks/archive/<月>/*/ 下的 task.json 都不丢失、不损坏（F54：递归 archive + strict 读）
7. journal 编号从 1 开始且无 gap
8. Python ≥ 3.9
9. 脏文件数（仅 informational，不返非零）
```

### 8.2 --fix 模式

`--fix` 会自动修复大部分 Warning，**也能修复 2 类 Problem**（`.developer` 缺失、stale `.current-task` 指针）：

- 恢复 `.developer`：workspace/ 恰好 1 个子目录时恢复真名（保住 journal 可达），否则补默认 developer；同时覆盖“文件缺失”和“无 name= 行”两种损坏形态（第 9 轮 P2-1）
- 补齐丢失的子目录（含 stray-file 恢复：路径被普通文件占用时先清理再建）
- 创建 workspace 和首个 journal
- 清理指向丢失目录的 `.current-task` 指针

**不会自动修复**：
- `task.json` 损坏（需要人判断：手动修复，或 `task delete --force <name>` 丢弃；doctor 不会替你清 `.current-task` 指向的损坏任务）
- journal 编号 gap（可能是你手动删的）

### 8.3 使用场景

```bash
# 每天早上：早上提醒“项目状态是否健康”
python3 trellis.py doctor

# 遇到不可解释的 bug：可能是状态损坏
python3 trellis.py doctor --fix

# pre-commit hook 自动跑（安装时提供）
# hook 失败 → commit 被拒绝 → 提示你跑 doctor --fix
```

**反面**：手动 rm -rf `.trellis-lite/tasks/`，期望 doctor 恢复任务内容 —— **不行**，doctor 只能修复指针与目录，不能恢复已删的 task.json。

---

## 九、install/uninstall 生命周期

`install.sh` 与 `uninstall.sh` 必须作为一对使用。**install 创建的每个工件，uninstall 都能清理**。

### 9.1 install 创建什么

| 工件 | 触发条件 |
|---|---|
| `.trellis-lite/` 目录 | 始终 |
| `.trellis-lite/.developer` | init 阶段（仅首次安装） |
| `AGENTS.md` | `--platforms qoder/opencode/all`（仅首次） |
| `CLAUDE.md` | `--platforms claude/all`（仅首次） |
| `.clinerules/trellis-lite.md` | `--platforms cline/all`（仅首次） |
| `.gitignore` runtime 块 | 目标存在 .gitignore（仅首次） |
| `.git/hooks/pre-commit` | 目标存在 `.git/`（仅首次） |

### 9.2 uninstall 清理什么

- `.trellis-lite/` 整个目录（递归）
- `AGENTS.md` / `CLAUDE.md`（如果存在）
- `.clinerules/trellis-lite.md`（如果存在）+ 空目录 rmdir
- `.gitignore` 中的 Trellis 块（`# Trellis Lite runtime` marker + 下属 runtime 条目）
- `.git/hooks/pre-commit`（**仅当包含 "Trellis Lite" 字符串**，否则不动）

### 9.3 关键设计点

- **不覆盖用户的 hook**：uninstall 只删含 `Trellis Lite` 字符串的 hook（宽松匹配——整个 hook 是 Lite 的才删）
- **不覆盖用户的 .gitignore 行**：awk 状态机只在 `# Trellis Lite runtime` marker 块内删除 `.trellis-lite/.X` 条目，用户内容跨用户行保留
- **marker 锚定**：`.gitignore` marker 检测用 `grep -qxF` 锚定整行 + 字面匹配——散文中提到 "Trellis Lite runtime" 不会误触发清理（O14 修复点）
- **退出安全**：mktemp 临时文件在 EXIT trap 中清理（O15 修复点），即使 awk 失败也不会残留 /tmp
- **developer 保留**：`install.sh` 检测到 `.developer` 已存在时跳过 init（O16 修复点），不会静默覆盖用户手工设置的 dev name

### 9.4 完整生命周期演示

```bash
# 全新安装
cd ~/projects/my-app
/path/to/lite/install.sh . myname
python3 .trellis-lite/scripts/trellis.py context       # 验证

# 升级到新版 trellis-lite
cd /path/to/lite && git pull
cd ~/projects/my-app
/path/to/lite/uninstall.sh . && /path/to/lite/install.sh . myname

# 平时只想检查状态（不需要重装）
python3 .trellis-lite/scripts/trellis.py doctor

# 误装想全部回退
/path/to/lite/uninstall.sh .    # 清理所有 Trellis 工件
```

---

## 十、Sub-agent 分发：什么时候该用

### 决策树

```
任务规模？
├─ < 30 分钟    → 主 AI 直接干
├─ 30min-2h ─┬─ 跨 ≤ 5 文件 ─────→ 主 AI
│            ├── 涉及研究 ────────→ 分发 GeneralPurpose (调研)
│            └── 涉及多模块 ─────→ 分发 GeneralPurpose (实现)
└─ > 2 小时 ─┬─ 主 AI 写 PRD + Design
             ├── 分发 GeneralPurpose (实现)
             └── 分发 CodeReview (质量)
```

### Sub-agent Prompt 模板

```python
# GeneralPurpose - 实现
prompt = f"""
Active task: {trellis_current}
README: $REPO/{trellis_current}/prd.md

任务：按照 prd.md 实现目标代码。

步骤：
1. 读 prd.md 全文
2. 跑 `python3 .trellis-lite/scripts/trellis.py specs` 找出相关 spec
3. 读相关 spec 文件
4. 遵循现有代码风格（先读同目录的文件）
5. 实现
6. 跑项目的 lint/typecheck/test
7. 报告 findings（不要 commit，会由主 AI 询问用户）
"""

# CodeReview - 质量
prompt = f"""
Active task: {trellis_current}

任务：检查刚才的实现质量。

步骤：
1. 读 prd.md（Acceptance Criteria）
2. 读相关 spec
3. 读 git diff
4. 对每条 Acceptance Criteria 检查是否通过
5. 自修机械问题（lint、type、import）
6. 报告设计问题（不静默改）
7. 不要 commit
"""
```

### 关键原则

- **Prompt 必须以 `Active task: <path>` 开头**（sub-agent 否则找不到上下文）
- Sub-agent **不主动 commit**（统一由主 AI 问用户）
- 完成后 **必须回报** findings（不静默）
- 任务太大时分多次 sub-agent（一次 30-60 分钟）

---

## 十一、7 个最容易踩的坑

> 这些坑来自 25+ 项实战修复记录。每一项都已内置到 Lite 行为中——但你仍可能绕开。

### 坑 1：spec 不写 → 同样 bug 反复出现

**症状**：每 3 个任务 AI 都要重新问“项目用什么 ORM？”

**修法**：第一次确定后立刻写 spec。下次就一劳永逸。

### 坑 2：PRD 写到一半就开始实现

**症状**：AI 写 PRD → 突然改代码 → 后来发现方向错了

**修法**：`task start` 之前必须你确认 PRD。AI 不会自动 start。

### 坑 3：多个 in_progress 任务并存

**症状**：开了 3 个任务，每个都做一半，混乱

**修法**：
- 1 个时间只 1 个 in_progress（CLI 已会警告）
- 用 `task cancel <name>` 放弃当前、保留目录
- 用 `task finish`（状态 done）但仍可见

### 坑 4：session 不写 → 跨会话断片

**症状**：一个月后回来看 journal 空白，不知道当时在干嘛

**修法**：每个任务完成就**立刻** < 1 分钟写个 session。**未来你会感谢现在的自己**。

### 坑 5：期待 `install.sh` 重装会“修复”状态

**症状**：在老版本装的仓库上跑新版 `install.sh`，期望 dev name 被更新、模板被同步、hook 被升级。什么也没发生。

**修法**：重装是幂等跳过语义（详见第一节），不是“修复”。要全新初始化：先 `uninstall.sh .` 再 `install.sh . <name>`。要检查状态：跑 `doctor`。

### 坑 6：以为 `task finish` 丢了数据是工具的错

**症状**：`task finish` 返回 1，活跃指针还在，状态没变 —— 你以为工具坏了。

**修法**：**这正是设计意图**。`task finish` 在 task.json 损坏时会拒绝执行，因为它后续会调 `clear_current_task()` 清空活跃指针 —— 指针丢失不可逆。`task start` / `task archive` / `task cancel` **也**返 1（自第 6-7 轮 oracle-reviewer 后），理由同样：corrupted metadata + 副作用 = split-brain。详见第七节"退出码语义"。

### 坑 7：在散文中提到 “Trellis Lite runtime” → uninstall 误报清理

**症状**：你在 `.gitignore` 注释里写 `# Trellis Lite runtime monitoring explained`，跑 `uninstall.sh` → 输出“removed Trellis Lite runtime entries”但实际什么都没变。

**修法**：这是 0.6.10 已修复的 bug（O14）。升级后 grep 镋定到整行 + 字面匹配。如果你还在用旧版本，**不要在 .gitignore 注释里包含精确的 `# Trellis Lite runtime` 字符串**。

---

## 十二、日节奏建议

### 早上开始

```bash
# 1. 唤醒项目 + 体检
cd your-project
python3 .trellis-lite/scripts/trellis.py doctor
# → ✓ 全绿则跳过；⚠ warning 不阻 commit；✗ problem 必须修
python3 .trellis-lite/scripts/trellis.py context
# → 看 "Last session:" 知道上次在干啥
```

**为什么 `doctor` 在 `context` 之前？** 当 `.current-task` 指向一个已删除的目录、或 `task.json` 损坏时，`context` 会输出误导信息。先跑 `doctor [--fix]` 把环境整平，`context` 给出的状态才可信。

### 中途继续

打开 AI 工具 → "继续上次" → AI 调 `task current` → 读 PRD → 继续。

### 任务结束

```bash
git status  # 检查 dirty
python3 .trellis-lite/scripts/trellis.py task finish
# 写 spec（如有新发现）
git add -p && git commit -m "feat: ..."
python3 .trellis-lite/scripts/trellis.py task archive <name>
python3 .trellis-lite/scripts/trellis.py session --title "..." --summary "..." --commit <hash>
```

### 周末整理

```bash
python3 .trellis-lite/scripts/trellis.py task list --all
# 看看哪些 cancelled 太久 → 手动 rm -rf

ls -lh .trellis-lite/workspace/yourname/journal-*.md
# 超过 2000 行自动轮转，看起来不爽的可以手动合并
```

---

## 十三、跨会话恢复（最实用）

### 你隔了 2 周回来

```
你："接着做上次那个登录"

AI 路径：
1. task current → 找到 .trellis-lite/tasks/08-04-login
2. 读 prd.md → 回忆 Goal + Requirements
3. git log --oneline -10 → 看上次 commit
4. spec check → 当前 spec 状态
5. 接着实现剩下的 acceptance criteria
```

### 你想看看"上次那个 e2e 测试"怎么做的

```
你："上次 e2e-test 任务怎么做的？"

AI 路径：
1. task list --all → 找到 e2e-test（可能已 archived）
2. 读 workspace/you/journal-N.md → 找到对应 session
3. 读 prd.md → 当时的需求
4. 读 git log → 当时的 commit 历史
```

**5 步全部 read-only，不会意外改动代码**。

---

## 十四、PRD + Spec 真实示例

### 任务：加用户登录

`.trellis-lite/tasks/08-04-login/prd.md`：

```markdown
# 用户登录

## Goal
用户能用邮箱密码登录，错误 5 次锁定 30 分钟。

## Requirements
- POST /api/login { email, password } → 200 { token } / 401 { error }
- 错误 5 次锁定 30 分钟（Redis 计数）
- JWT HS256 24h 过期

## Acceptance Criteria
- [ ] 正确凭证返回 200 + JWT
- [ ] 错误密码返回 401 + 计数 +1
- [ ] 第 6 次错误返回 429 + Retry-After: 1800
- [ ] 30 分钟后自动解锁
- [ ] JWT 24h 后过期

## Notes
- 已有 argon2 哈希在 users.password_hash
- 已有 Redis 实例在 redis://localhost:6379
- 不做刷新 token
- UI 已有 LoginForm 组件
```

### 配合 spec（之前任务发现也好）

`.trellis-lite/spec/api.md`：

```markdown
# API Patterns

## Rule: 响应包装
所有 API 响应：`{ data, error, meta }`

**Do:** `return { data: { token }, error: null, meta: {} }`
**Don't:** `return { token }` 或 throw

## Rule: 错误状态码
- 4xx = 客户端错误（用户能修）
- 5xx = 服务端错误（用户管不了）
- 429 = 限流，必须带 `Retry-After` header

## Rule: 认证失败响应
统一 `401 { error: { code: 'INVALID_CREDENTIALS', message: '...' } }`
**不要**告诉用户"邮箱不存在 vs 密码错"（信息泄露）
```

---

## 十五、效率对比（有 vs 没有 Trellis Lite）

| 维度 | 无 Trellis | 有 Trellis Lite |
|---|---|---|
| 跨会话恢复 | 0（必须从头读代码） | 5 分钟（Context + Journal） |
| AI 写规范代码 | 30% 概率 | 90%+（读 spec） |
| 你忘记"为什么这么写" | 经常 | 极少（journal + spec） |
| 多任务切换 | 混乱 | 1 active 强制 |
| 项目历史 | 散落在 commit | 任务维度聚类 |
| 总监回头看 | 痛苦 | 一目了然 |

---

## 十六、决策清单（TL;DR）

### ✅ DO

- 每个 session 写 journal
- 每个新发现写 spec
- 每个 5min+ 任务建 PRD
- 让 AI 写完后**问**你才 commit
- 1 个时间 1 个 in_progress（CLI 已会警告，需人工自律）
- PRD 用动词 + 数字 + 验收点
- **状态机异常时跑 `doctor --fix`**（不手动改 task.json）
- **重装前先 `uninstall.sh .` + `install.sh . <name>`**（install 是幂等跳过，不是修复）
- **mutating task 操作依赖返 1（`task finish` / `task start` / `task archive` / `task cancel` 在 corrupted `task.json` 时一致拒绝 + 副作用不执行，避免 split-brain）；可读操作总返 0（`task list` / `task current`）**
- **遇到不可解释的 bug 先 `doctor [--fix]`，再看 `git log`**

### ❌ DON'T

- 不要自动 commit
- 不要写空的 PRD
- 不要写“模糊”的 spec
- 不要跳过 update-spec 阶段
- 不要多个任务并行 in_progress
- 不要让 PRD 长过大半页（一页内能 review）
- **不要为单任务创建多个 `in_progress`**（CLI 不强制；用 `task finish` / `task cancel` 切换，或 `--replace` 显式接管）
- **不要期待 `install.sh` 重装会覆盖任何东西**（见第一节“重装语义”）
- **不要手动改 task.json**（会被 `doctor` 报 Warning，且会绕开 set_status 守门）
- **不要把 `task list` / `task current` 当 CI 闸门**（它们空状态返 0）

---

## 附录：参考文件

| 文件 | 作用 |
|---|---|
| `.trellis-lite/workflow.md` | 3 阶段工作流详细说明 |
| `.trellis-lite/skills/brainstorm.md` | Phase 1 需求发现 |
| `.trellis-lite/skills/before-dev.md` | Phase 2 写代码前必读 |
| `.trellis-lite/skills/check.md` | Phase 2 质量检查 |
| `.trellis-lite/skills/update-spec.md` | Phase 3 沉淀经验 |
| [usage-guide.md](usage-guide.md) | 完整使用示例 |
| [design.md](design.md) | 架构设计原理（含状态机模型、子命令表） |
| [exit-codes.md](exit-codes.md) | 退出码语义与可逆性原则（POSIX 风格） |
| [architecture-review.md](architecture-review.md) | 架构审查记录与债务清单 |
| [README.md](../README.md) | 快速上手 |
