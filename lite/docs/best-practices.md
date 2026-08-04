# Trellis Lite — 最佳实践指南

> 基于 4 轮审查沉淀 + 1280 行实现 + 104 个测试覆盖的实战经验。
>
> 配套文档：
> - [README.md](../README.md) — 快速上手
> - [design.md](design.md) — 设计原理与架构
> - [usage-guide.md](usage-guide.md) — 完整使用示例
> - [workflow-checklist.md](workflow-checklist.md) — 任务级 checklist（可复制）
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
```

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

## 六、Sub-agent 分发：什么时候该用

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

## 七、4 个最容易踩的坑

> 这些坑来自 25 项实战修复记录。每一项都已内置到 Lite 行为中——但你仍可能绕开。

### 坑 1：spec 不写 → 同样 bug 反复出现

**症状**：每 3 个任务 AI 都要重新问"项目用什么 ORM？"

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

---

## 八、日节奏建议

### 早上开始

```bash
# 1. 唤醒项目
cd your-project
python3 .trellis-lite/scripts/trellis.py context
# → 看 "Last session:" 知道上次在干啥
```

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

## 九、跨会话恢复（最实用）

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

## 十、PRD + Spec 真实示例

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

## 十一、效率对比（有 vs 没有 Trellis Lite）

| 维度 | 无 Trellis | 有 Trellis Lite |
|---|---|---|
| 跨会话恢复 | 0（必须从头读代码） | 5 分钟（Context + Journal） |
| AI 写规范代码 | 30% 概率 | 90%+（读 spec） |
| 你忘记"为什么这么写" | 经常 | 极少（journal + spec） |
| 多任务切换 | 混乱 | 1 active 强制 |
| 项目历史 | 散落在 commit | 任务维度聚类 |
| 总监回头看 | 痛苦 | 一目了然 |

---

## 十二、决策清单（TL;DR）

### ✅ DO

- 每个 session 写 journal
- 每个新发现写 spec
- 每个 5min+ 任务建 PRD
- 让 AI 写完后**问**你才 commit
- 1 个时间 1 个 in_progress
- PRD 用动词 + 数字 + 验收点

### ❌ DON'T

- 不要自动 commit
- 不要写空的 PRD
- 不要写"模糊"的 spec
- 不要跳过 update-spec 阶段
- 不要多个任务并行 in_progress
- 不要让 PRD 长过大半页（一页内能 review）

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
| [design.md](design.md) | 架构设计原理 |
| [README.md](../README.md) | 快速上手 |
