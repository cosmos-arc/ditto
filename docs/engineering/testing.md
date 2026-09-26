# Ditto 测试指南

本页记录项目特有的测试合同；命令事实源仍是 `Taskfile.yml`、`pyproject.toml` 和 CI。

## 按风险验证

Bug 先复现能解释问题的失败，再验证修复及回归；公共契约、PIT、风控、交易、执行、组合会计和回测语义使用相应边界与反例测试。普通可逆改动按可观察结果验收，不要求证明固定的编辑顺序。

纯文档、格式化、纯移动、生成镜像和机械重命名检查入口及行为未意外变化即可。行为测试通过既有公共入口观察结果，不用仅断言内部调用细节的 mock 代替实际行为。

审查判定、修复批次和复审范围以[交付约定](development-workflow.md#cr-判定与收敛)为准；
验证明确未测范围和剩余风险，不要求固定 reviewer 数、主观评分或每个任务的完整评分表。

## 修复与反馈顺序

先运行上次失败的对应门及相关格式、类型等廉价检查，再按风险执行宽范围验证。
复用根 Task 的入口；专项用于快速定位，最终范围仍由本页和 changed-scope 决定。
真实 provider 留存载荷、DI/存储及共享消费者的变更要由相应实际入口验收，不能仅用
富化夹具或 mock 证明真实路径可用。

CI 失败先读取失败 job 日志，记录 SHA、命令和失败原因；确定性缺口在本地通过对应
门后再提交下一合并候选。环境无法复现时记录限制和剩余阻断，由新 SHA 的对应 CI
补证。代码未变且已证实为基础设施故障时重跑原 SHA 的失败 job；行为、类型、覆盖率
等确定性失败通过修复解决，不以重跑掩盖。

`task check-web` 的普通测试不证明 CI 的覆盖率门通过；涉及 Web 生产代码的送审批次
或修复 Web 覆盖率失败时，使用现有 `task web-quality` 复核，阈值以配置为准。
测试通过、覆盖率通过、系统旅程通过分别报告，不能互相替代。

同一未变化内容上，若正常 pre-push 将执行所需完整验证，专项通过后交由该入口完成，
避免先手动重复运行同套全量检查。明确所需范围仍须执行，hooks 不跳过；内容变化
重新验证受影响范围，旧 SHA 结果不替代最终提交 CI。本机完整验收保持单套运行。

## 测试层次

- 单元测试：靠近 owner package，覆盖纯领域规则、边界值和错误语义。
- 集成测试：覆盖 storage、DI、API、跨组件合同和序列化；不得把真实外部服务当作默认依赖。
- Golden/E2E：验证合成数据的完整用户路径；真实数据 E2E 需要 token、显式授权和独立证据。
- PIT：使用 `@pytest.mark.pit`，包含未来哨兵、截止边界和允许数据的对照断言。

测试应确定、隔离且可并行。时间、随机数、外部 I/O 与 source snapshot 必须显式控制；失败后清理临时状态。

`scripts/test.py` 在启动 pytest 前为子进程固定 `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`，
覆盖收集阶段、xdist worker 和测试创建的子进程。显式真实数据验收通过独立入口运行，
不得依赖默认自动化测试读取个人钥匙串。

Registry 配置测试通过近端 `conftest.py` 临时安装现有 keyring 包的 null backend，
保留真实 ConfigProvider 装配，但不读取宿主钥匙串；每项测试结束恢复原 backend。
测试具体密钥行为时显式注入固定值，生产密钥读取和显式真实数据 E2E 不受此 fixture 影响。

本机完整验收通过根 `task check` 编排；不要另起同一套后端和 Web 门禁并行抢占
资源。集中出现交互测试超时时，先单独复现并排查资源争用，不直接增加超时或重试次数。

## 常用命令

```bash
# 单个测试或包
uv run --no-sync pytest packages/data/tests/test_example.py -q
uv run --no-sync pytest packages/data/tests

# 项目包装命令
task test -- --fast
task test
task test -- --integration
task test -- --cov-xml

# 专项
uv run --no-sync pytest -m pit
task type -- --tests
```

仅测试 diff 仍需 Ruff format-check/lint 和测试类型检查。普通单包生产改动运行对应包测试、Ruff 与类型检查；跨包、契约、依赖、架构或工具链改动运行 `task check`。远端 CI 是权威合并门，本地通过不替代 CI。

## 覆盖率与证据

覆盖率阈值以 [.github/codecov.yml](../../.github/codecov.yml) 和 Web 的
[vitest.config.ts](../../apps/web/vitest.config.ts) 为准，不在说明中复制数值。覆盖率不是新增无意义断言的目标。优先证明正常路径、边界、失败恢复、PIT 隔离和关键状态转换。

最终报告只列实际运行过的命令。平台、依赖或外部凭证使检查无法运行时，说明精确原因和剩余风险。

## 可选历史质量比较

普通审视报告事实、影响和建议。仅在明确要求历史可比评分时，显式选择 rubric 与范围并记录版本、基线提交和测量覆盖。
旧口径定义固定为 [legacy-v1（688386be）](https://github.com/cosmos-arc/ditto/tree/688386be200af5fd8d92e138575f55f283b5dd05/.agents/skills/ditto-quality-eval)，包括分项表、权重、封顶规则及报告结构；它仅用于复现历史报告，不是当前 CI 或编码规则。
按该口径 pass/warning/fail 分别取 100%/60%/0%，not_measured 从分母排除并披露缺口；仅在同口径、同范围下比较。每个基线命令采集一次，不把静态政策 fixture 当作模型行为证据。
