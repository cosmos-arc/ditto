# Ditto 测试指南

本页记录项目特有的测试合同；命令事实源仍是 `pixi.toml`、`pyproject.toml` 和 CI。

## 何时必须先 RED

Bug、行为变化、公共契约、PIT、风控、交易、执行、组合会计和回测语义必须先添加或定位能解释风险的测试，并实际观察其以预期原因失败。随后做最小 GREEN，实现稳定后再重构。

纯文档、格式化、纯移动、生成镜像和机械重命名豁免。若机械改动触及行为，立即恢复 RED → GREEN 流程。

记录 RED 时保留精确命令、失败断言/错误和它为何证明问题。不要用只断言内部调用细节的 mock 代替可观察行为。

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

本机完整验收通过根 `pixi run -e dev check` 编排；不要另起同一套后端和 Web 门禁并行抢占
资源。集中出现交互测试超时时，先单独复现并排查资源争用，不直接增加超时或重试次数。

## 常用命令

```bash
# 单个测试或包
pixi run -e dev pytest packages/data/tests/test_example.py -q
pixi run -e dev pytest packages/data/tests

# 项目包装命令
pixi run -e dev test --fast
pixi run -e dev test
pixi run -e dev test --integration
pixi run -e dev test --cov-xml

# 专项
pixi run -e dev pytest -m pit
pixi run -e dev type --tests
```

仅测试 diff 仍需 Ruff format-check/lint 和测试类型检查。生产 Python、依赖、架构或配置 diff 运行 `pixi run -e dev check`。

## 覆盖率与证据

CI 的分支覆盖率门槛是 80%，但覆盖率不是新增无意义断言的目标。优先证明正常路径、边界、失败恢复、PIT 隔离和关键状态转换。

最终报告只列实际运行过的命令。平台、依赖或外部凭证使检查无法运行时，说明精确原因和剩余风险。
