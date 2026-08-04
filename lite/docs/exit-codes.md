# Trellis Lite 退出码约定

> 配套文档：[README](../README.md) · [usage-guide](usage-guide.md) · [design](design.md)

Trellis Lite 遵循 POSIX 风格的退出码约定，**shell 脚本和 CI 可以安全依赖**：

| 退出码 | 含义 | 触发场景示例 |
|---|---|---|
| **0** | 成功 | 命令正常完成；或在"读取"类命令中，**查询对象为空**（如 `task list` 没有任务；`task current` 没有活跃任务）—— 这些是合法的状态，不是错误 |
| **1** | 用户错误 | 用法错误（缺参数、未知子命令）；输入校验失败（任务名为空、名称非法）；目标不存在（`task start ghost`）；状态不允许（如 `task delete` 拒绝非 cancelled；`task finish` 没有活跃任务） |
| **2** | （保留） | 计划用于环境错误（Python 版本不对、磁盘不可写等）。目前所有错误均归入 1 |
| **其它** | 系统错误 | 由 Python / bash 自身产生（如文件权限、IO 异常） |

## 设计依据

### 为什么"空状态"返回 0 而不是 1？

`task list`、`task current`、`specs`、`context` 等是**读取类命令**。调用方往往这样写：

```bash
if python3 trellis.py task list | grep -q "$NAME"; then
    ...
fi
```

如果"无任务"返回 1，shell `set -e` 会让脚本意外中止。
**返回 0 + 空输出**是 git、ls、find 等 Unix 工具的标准做法。

### 为什么"用法错误"返回 1 而不是 2？

POSIX 建议 1 = 一般错误，2 = 用法错误。但 Trellis Lite 的错误面较小（CLI 而非 daemon），**区分 1 和 2 收益低**。统一为 1 减少心智负担。

### 为什么 `task finish` 在"无活跃任务"时返回 1？

这是用户**主动请求修改状态**，但当前状态不允许。区别于 `task list` 这种**被动查询**。

## 在 shell 中使用

```bash
# 单条命令：依赖 0/1 决定下一步
if ! python3 trellis.py task finish; then
    echo "no active task — nothing to finish"
    exit 1
fi

# 配合 set -e：失败的命令会中止脚本
set -e
python3 trellis.py task create "deploy" --slug deploy
python3 trellis.py task start deploy
# 如果 start 失败（任务不存在或网络异常），脚本立即退出

# 循环中：明确区分"创建失败"和"已是最新"
for slug in feat-a feat-b; do
    python3 trellis.py task create "$slug" --slug "$slug" || \
        echo "skip: $slug already exists"
done
```

## 在 CI / pre-commit 中使用

```yaml
# GitHub Actions
- name: Verify trellis state
  run: python3 .trellis-lite/scripts/trellis.py doctor
  # doctor 在健康时返回 0；发现问题返回 1
```

```bash
# pre-commit hook
python3 .trellis-lite/scripts/trellis.py doctor || {
    echo "Trellis state unhealthy. Run 'doctor --fix' to repair."
    exit 1
}
```

## 当前实现的合规性

| 函数 | 退出码 | 是否符合约定 |
|---|---|---|
| `cmd_init` | 0/1 | ✓ |
| `cmd_task` (dispatch) | 0/1 | ✓ |
| `_task_create` | 0/1 | ✓ |
| `_task_start` | 0/1 | ✓ |
| `_task_current` | 0 | ✓（"无活跃"=合法状态） |
| `_task_finish` | 0/1 | ✓ |
| `_task_archive` | 0/1 | ✓ |
| `_task_cancel` | 0/1 | ✓ |
| `_task_list` | 0 | ✓（"无任务"=合法状态） |
| `_task_delete` | 0/1 | ✓ |
| `cmd_session` | 0/1 | ✓ |
| `cmd_context` | 0 | ✓（总是成功，无错误路径） |
| `cmd_specs` | 0 | ✓ |
| `cmd_version` | 0 | ✓ |
| `cmd_doctor` (planned) | 0/1 | ✓ |

未达成一致时，以本表为准修改代码。