# Trellis Lite 流程质量分析报告

> 审阅日期：2026-08-08 · 审阅范围：完整工程（设计文档、trellis.py 实现、skills、tests、实际任务产物）

## 一、总体评估

| 维度 | 评分 | 评语 |
|------|------|------|
| 流程设计完整性 | A+ | 3 阶段（PLAN→CODE→WRAP）清晰、自洽、无冗余 |
| 工程实现质量 | A+ | 1889 行单文件、零依赖、~166 个 unittest、19 轮审查加固 |
| 文档完备性 | A+ | 设计文档、最佳实践、checklist、CLI 手册、架构审查记录齐全 |
| 可执行性（AI 遵守度） | B | 流程依赖 AI 自律，存在"跳过 WRAP"的实际证据 |
| 健壮性/防御性 | A+ | 状态机强制、路径穿越防护、损坏恢复、幂等设计 |

总体评级：A（设计优秀，执行依赖外部约束）

## 二、架构与实现亮点

### 2.1 状态机设计

```
planning ──(task start)──→ in_progress ──(task finish)──→ done ──(task archive)──→ archived
     │                         │                              │
     │                         │                              └──(task cancel)──→ cancelled
     └─────────────────────────┴──────── 也可以直接 archive ──────────────────────┘
```

- forward-only 转移，禁止回退
- 幂等性：重复 task start 是安全 no-op
- 终态保护：archived/cancelled 不可再转移
- 唯一反向通道：done → cancelled 允许反悔

### 2.2 防御性编程

| 威胁 | 防御机制 |
|------|----------|
| 路径穿越（--slug ../../evil） | slugify() 只保留 [a-z0-9-]，非 ASCII 用 md5 hash |
| 任务名注入（archive 保留字） | resolve_task_dir() 显式拒绝 |
| 损坏的 task.json | read_json_strict() + doctor --fix 恢复 |
| 目录结构损坏 | _safe_mkdir() 透明恢复 stray file → directory |

### 2.3 测试覆盖

~166 个 unittest 覆盖每条 CLI 路径：状态机锁定、任务全生命周期、doctor 自检、
session 轮转、安装幂等性、slugify fuzz（1000 随机 Unicode）、Usage 一致性。
测试哲学："行为覆盖 > 覆盖率百分比"（subprocess 隔离导致 coverage.py 无法跨进程跟踪）。

## 三、关键发现：流程执行缺口

当前 todolist 任务的状态揭示了执行偏差：

| 证据 | 状态 | 分析 |
|------|------|------|
| task.json | status: "done" | 任务已标记完成 |
| prd.md | 验收标准全部 - [ ] 未勾选 | CODE 阶段质量检查未执行 |
| todolist/ | 目录不存在 | 交付物未产生或未提交 |
| journal-1.md | 只有标题 | WRAP 阶段 session 记录未执行 |

根本原因：所有约束是建议性的，没有强制性。task finish 不检查 PRD 勾选状态，
task archive 不检查 journal 记录，context 不提醒"上一任务未完整闭环"。

## 四、文档体系评估

10 份文档覆盖 AI 入口（AGENTS.md/CLAUDE.md）、流程定义（workflow.md）、
行为指导（skills/×4）、开发者文档（docs/×8）。文档与实现高度一致。
轻微不一致：design.md 说 165 个测试，best-practices.md 说 166 个。

## 五、与原版 Trellis 对比

| 维度 | 原版 | Lite | 评估 |
|------|------|------|------|
| 脚本数量 | 28 个 | 1 个（1889 行） | ✅ 极简 |
| 外部依赖 | pnpm + Node | 纯 Python 标准库 | ✅ 零依赖 |
| 工作流 | 4 阶段 | 3 阶段 | ✅ 去冗余 |
| 上下文注入 | JSONL 清单 | AI 直接读 markdown | ⚠️ 能力降级但合理 |
| 跨会话 Memory | 语义检索 | Markdown 日志轮转 | ⚠️ 降级但成本极低 |

## 六、改进建议（含落地方案）

> 设计原则：所有改进保持 **警告而非阻塞**，符合 Lite "协议而非强制"的哲学；
> 全部复用现有 helper（read_json_strict / git_status_porcelain / colored），
> 不引入新依赖；每项改进附带对应测试。

### 改进 1：task finish 检查 PRD 验收标准未勾选（高优先级）

**问题**：todolist 任务 `status=done` 但 prd.md 验收标准 5 条全部 `- [ ]` 未勾选。

**方案**：在 `_task_finish()`（trellis.py:839）状态更新成功后、打印 ✓ 之前，
扫描 `prd.md` 中的未勾选项，发出黄色警告：

```python
# 插入位置：trellis.py 第 895 行 clear_current_task() 之前
def _count_unchecked_criteria(task_dir: Path) -> int:
    """Count '- [ ]' items in prd.md. Returns 0 if prd.md missing/unreadable."""
    prd = task_dir / "prd.md"
    if not prd.is_file():
        return 0
    try:
        return sum(
            1 for line in prd.read_text(encoding="utf-8").splitlines()
            if re.match(r"^\s*-\s*\[ \]", line)
        )
    except OSError:
        return 0

# _task_finish 中（第 885 行 set_status 成功之后）：
unchecked = _count_unchecked_criteria(task_dir)
if unchecked:
    print(colored(
        f"Warning: prd.md has {unchecked} unchecked acceptance criteria. "
        f"Verify them or check them off before archiving.",
        C_YELLOW,
    ))
```

**交互示例**：
```
✓ Task finished: .trellis-lite/tasks/08-08-todolist
Warning: prd.md has 5 unchecked acceptance criteria. Verify them or check them off before archiving.
  Run 'task archive <name>' when ready to archive.
```

**兼容性**：纯警告，exit code 不变；prd.md 缺失时静默（返回 0）。
**测试**：test_task.py 增加 `test_finish_warns_on_unchecked_criteria` /
`test_finish_silent_when_all_checked` / `test_finish_silent_when_prd_missing`。

### 改进 2：task archive 增加 WRAP 完整性提示（高优先级）

**问题**：todolist 任务从未运行 `session`（journal-1.md 为空），spec 未更新，
WRAP 阶段完全缺失，但 archive 可以无声通过。

**方案**：在 `_task_archive()`（trellis.py:901）状态预检通过后、shutil.move 之前，
做两项只读检查并汇总警告：

```python
def _wrap_completeness_warnings(tdir: Path) -> list[str]:
    """Read-only WRAP-phase checks. Returns human-readable warnings (may be empty)."""
    warnings: list[str] = []
    # (a) journal 是否有任何 session 条目（不只标题行）
    ws = get_workspace_dir()
    if ws and ws.is_dir():
        journals = list_journals(ws)
        has_entry = any(
            re.search(r"^## \d{4}-\d{2}-\d{2}", j.read_text(encoding="utf-8"), re.M)
            for _, j in journals
        ) if journals else False
        if not has_entry:
            warnings.append("no session recorded (run 'session --title ... --summary ...')")
    # (b) spec/ 是否有未提交变更
    spec_dirty = any(
        line[1:].strip().startswith(f"{TRELLIS_DIR}/{DIR_SPEC}/")
        or line[1:].strip().startswith(f"{DIR_SPEC}/")
        for line in git_status_porcelain().splitlines()
    )
    if spec_dirty:
        warnings.append("spec/ has uncommitted changes (commit them with or after the task)")
    return warnings

# _task_archive 中（第 947 行 set_status 成功之后）：
for w in _wrap_completeness_warnings(get_trellis_dir()):
    print(colored(f"Warning (WRAP incomplete): {w}", C_YELLOW))
```

**兼容性**：archive 照常成功（exit 0）；检查全部只读，失败静默降级为空列表。
**测试**：test_task.py 增加 `test_archive_warns_when_no_session` /
`test_archive_warns_on_uncommitted_spec`；用例需 mock/构造 git 仓库（Harness 已有模式）。

### 改进 3：context 输出"最近任务的闭环状态"（中优先级）

**问题**：AI 开始新会话时运行 `context`，看不到上一个任务是否完整走完 WRAP，
跨会话连续性断链。

**方案**：在 `cmd_context()`（trellis.py:1269）的 Active task 段之后，
输出最近一个非 archived 任务的健康度：

```
Task:    .trellis-lite/tasks/08-08-todolist [done]
WRAP:    ⚠ prd 5 unchecked · no session recorded
```

实现要点：复用改进 1/2 的 `_count_unchecked_criteria` 与 `_wrap_completeness_warnings`，
对 `task list` 中最新非 archived 任务运行；无任务时不输出该行（保持现有输出契约）。
**测试**：test_context_specs_help.py 增加 `test_context_shows_wrap_status`。

### 改进 4：task list 增加健康度列（中优先级）

**方案**：`_task_list()`（trellis.py:1053）每行追加 health marker：

```
  08-08-todolist        [done]        ⚠ wrap-incomplete
  07-26-login-api       [archived]    ✓
```

规则：`archived` 且无警告 → `✓`；`done` 且有警告 → `⚠ wrap-incomplete`；
`cancelled` → `-`（不适用）；`planning/in_progress` → 空（尚未到 WRAP）。
注意性能：只对 done/archived 任务运行检查，避免 list 大仓库时逐任务读 prd.md 变慢
（可加 `--no-health` 开关兜底，默认开启）。
**测试**：test_task.py 增加 `test_list_shows_health_marker`。

### 改进 5：doctor 增加"流程完整性"第 10 项检查（中优先级）

**方案**：新增 `_check_wrap_completeness(tdir, warnings)`（trellis.py:1835 `_doctor_finish` 之前注册）：
- 遍历 `tasks/` 下所有 `status=done` 任务
- 复用改进 1/2 的检查函数
- 每个不完整任务产生一条 warning（非 problem，不阻塞 exit 0）

```
Warnings (2):
  - task 08-08-todolist: prd.md has 5 unchecked acceptance criteria
  - task 08-08-todolist: no session recorded
```

**测试**：test_doctor.py 增加 `test_doctor_warns_on_wrap_incomplete_task`。

### 改进 6：pre-commit hook 集成（低优先级）

**现状**：hooks/pre-commit 已能阻塞孤儿任务（test_precommit.py:72）。
**方案**：扩展 hook，对已 `done` 但未 archive 且 WRAP 不完整的任务打印提醒（不阻塞 commit，
因为 Lite 规则是"commit 前问用户"，hook 只做提示）。改动集中在 hooks/pre-commit +
install.sh 的 hook 部署逻辑；test_precommit.py 增加对应用例。

### 改进 7：session 自动关联当前任务（低优先级）

**方案**：`cmd_session()`（trellis.py:1179）在 `--title` 缺省时，
若存在活跃任务则用其 title 作为默认标题，journal 条目自动附
`Task: <path>` 行。零破坏：显式传参时行为完全不变。

### 改进 8：task create --template（低优先级）

**方案**：`--template bug|feature|refactor` 选择预填充的 prd.md 模板
（模板文件放 .trellis-lite/templates/，init 时生成默认三份）。
USAGE 字典增加对应条目；test_usage_consistency.py 的 expected keys 需同步。

## 六之附：落地路线图

| 批次 | 内容 | 依赖 |
|------|------|------|
| Batch 1（闭环核心） | 改进 1 + 2（finish/archive 警告）+ 各自测试 | 无 |
| Batch 2（可见性） | 改进 3 + 4（context/list 健康度） | 依赖 Batch 1 的共用检查函数 |
| Batch 3（体检） | 改进 5（doctor 第 10 项） | 依赖 Batch 1 |
| Batch 4（体验） | 改进 6/7/8 | 独立，可按需挑选 |

抽取共用函数 `_count_unchecked_criteria` 与 `_wrap_completeness_warnings`
到 trellis.py 的 helpers 区（紧随 set_status 之后），避免四处复制逻辑。

## 七、结论

Trellis Lite 是设计精良、实现扎实、文档完备的轻量级 AI 辅助工作流系统。
核心价值：正确的极简主义 + 防御性工程 + 文档即代码。
最大风险不是技术缺陷，而是流程遵守度——系统提供完美轨道，但 AI 可以选择不走。
短期建议：在 task finish/archive 增加非阻塞的完整性提示，以最小成本闭环 WRAP 阶段。
