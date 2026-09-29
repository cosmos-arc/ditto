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

同一未变化内容上，若送审前的 `task verify-push` 将执行所需完整验证，专项通过后交由该
入口完成，避免先手动重复运行同套全量检查。明确所需范围仍须执行，hooks 不跳过；内容变化
重新验证受影响范围，旧 SHA 结果不替代最终提交 CI。本机完整验收保持单套运行。

## 测试层次

- 单元测试：靠近 owner package，覆盖纯领域规则、边界值和错误语义。
- 集成测试：覆盖 storage、DI、API、跨组件合同和序列化；不得把真实外部服务当作默认依赖。
- Golden/E2E：验证合成数据的完整用户路径；真实数据 E2E 需要 token、显式授权和独立证据。
- PIT：使用 `@pytest.mark.pit`，包含未来哨兵、截止边界和允许数据的对照断言。

## 入口一致性与标记语义（#330 B1）

目录到层级的映射由**单一规则**解释：`tooling/quality/pytest_layering.py` 经仓库根
`conftest.py` 注册，对单文件、owner、全仓与 CI 分片（含 `-o addopts=` 重建参数的
子系统）入口一致生效。规则取**仓库根相对路径**里最后一个 `tests` 目录之后的组件
精确匹配（检出路径祖先不参与——无论祖先叫 `integration`、`unit` 还是 `tests`）：

| tests 树内含目录 | 追加标记 |
| --- | --- |
| `integration` | `integration` + `serial` |
| `unit` | `unit` |
| `contract`（apps/backend） | `integration` |
| `e2e`（apps/backend） | `e2e` |
| 其余（registry、benchmarks、`tooling/*/tests`） | `unit` |

文件名子串不参与判定；测试上的显式标记保留并叠加。近端 conftest 不得修改外国
owner 的标记或收集（历史上的四个按路径加标钩子已移除）；conftest 里的 `pytestmark`
从不生效，层级声明放测试模块。`integration` 目录附带 `serial` 是继承自旧钩子的
blanket 资源策略，串行审计（#226）已开始按真实资源逐树解除——解除入口是 layering
规则里的 `_SERIAL_OPT_OUT_TREES` 登记表（整组件前缀匹配），不在各包 conftest；
登记只去掉层级附带的 `serial`，`integration` 层级保留，显式 `@pytest.mark.serial`
照常叠加（树内单文件回退口）。

**串行审计（#226）现状**：审计维度 = 共享 DB/文件/工作区、端口、线程/进程、全局
init、外部资源；结论必须来自实际证据（fixture/路径/进程审计 + 配对并行对照），
不来自"连续绿"。CI 分片的六个 shard 与 capacity 慢道各自跑在独立 GitHub runner
（独立检出/文件系统），跨 runner 不存在可共享的写路径——`serial` 从来只约束单
runner 内的 xdist worker。各 integration 树处置：

| 树 | 资源审计结论 | 处置 |
| --- | --- | --- |
| `packages/data/tests/integration` | 每例独立 DB（`:memory:`/`tmp_path`/`mkstemp`），schema.sql 只读模板按 worker 复用，无端口/子进程/跨例全局 init；触网用例无 token 即 skip；唯一无门控的联网用例（tushare 无效 token 错误处理）已打 `slow` 退出 fast 车道 | **已解除**（试点，2026-09） |
| `packages/application/tests/integration` | 零 session fixture/env 写/子进程/端口/网络（conftest 仅 docstring）；`_support` 模块纯不可变常量；非 tmp 文件为纯内存 mock 或只读模板渲染；capacity 子集已自带标记 | **已解除**（第二批 #359，2026-09） |
| `packages/backtest/tests/integration` | 806 行 conftest 全 function 级 fixture，parquet 每例 `tmp_path` 再生，模块级仅不可变常量；全树 0.7s | **已解除**（第二批 #359，2026-09） |
| `apps/backend/tests/integration` | session 级 Prefect test harness（真实子进程/端口）、全局 observability init、env 覆盖 | 保留串行；解除需先按 worker 隔离 Prefect harness，另立票 |
| `packages/platform/tests/integration`（observability 树） | 等待治理与状态恢复已收口（#348，2026-09）：每例快照/摘挂/恢复 OTel API 全局，外来 provider 不被 teardown 关闭；生产 OTLP 传输走本地真实 sink（`127.0.0.1:0` 临时端口，daemon 线程 fixture 拆除收敛）；`os.chdir` 两处均 `finally` 恢复；fixtures 全 function 级 | **已解除**（第三批 #363，2026-09） |
| `packages/analysis/tests/integration` | 无 conftest；全 `tmp_path`，`monkeypatch.setenv` 自动恢复，`importlib.resources` 与 fixtures 目录只读 | **已解除**（第三批 #363，2026-09） |
| `packages/strategy/tests/integration`（alpha） | conftest 纯 helper/不可变常量（零 fixture 声明）；唯一 fixture 纯内存 polars 构造；parquet 每例 `tmp_path` 再生 | **已解除**（第三批 #363，2026-09） |
| `packages/execution/tests/integration` | #347 试点新树：真实 SQLite 持久化（paper 会话库恢复/防篡改组）自 unit 迁入；每例独立 `:memory:` pool fixture，conftest 仅 sqlite fixtures（store 实现已核实零 observability 依赖），无文件/端口/线程/子进程/env 写 | **已解除**（随 #347 迁移登记，2026-09；证据同 #226 形态：配对×5/注入/车道） |

CPU/内存容量型慢测试与串行策略分开：它们打 `slow`/`capacity` 进慢道，不是保留
`serial` 的理由。旧"4 片/-n2/<5min"目标仅作历史参考。**恢复策略**：任何可复现的
并发故障，先给受影响文件加显式 `@pytest.mark.serial` 立即恢复隔离并保留复现，
再决定是否撤登记表条目；若故障证明的是跨 runner 作用域问题，不得以恢复旧 blanket
标记宣称解决——互斥必须在正确作用域实现。

**同语境重复执行消除与证据核验（#350）**：PIT 标记套件与 OpenAPI conformance
在 CI 里曾各执行两次（分片并行道全量一次 + 专用重跑一次：backend-tests 内
`task pit` 59.6s 串行尾部、api-contract 内整文件 conformance 重跑）。现统一由
分片承载唯一执行，backend-tests 以 `tooling/quality/required_suite_evidence`
从产物 fail-closed 核验：inventory（含 pit 标志）⊆ nodes 选择恰一次 + 每道
junit 计数与选择数一致且 errors=0——清单漂移、缺清单（标记不再匹配任何收集项）、
漏用例、重复选择、junit 短计均立即失败。负向验收覆盖于
`tooling/quality/tests/test_required_suite_evidence.py`。本地链条不变
（`task pit`/`check-contract` 保留具名门），CI 钉死更新保真原意图：PIT 与
conformance 仍是显式 CI 门，只是从盲重跑升级为执行+产物证明。

**真实持久化与装配接缝的落位（#347 试点，承接 #339 迁移决议四组之二）**：真实
存储（真 SQLite/文件 reopen、防篡改恢复）归**集成职责**，所有权仍在能力包——
迁移是目录归属变化，不是把 mock 换成真库或反之；同文件混合 mock 接缝与真库
接缝时按用例拆分，不批量搬同目录所有测试。纯符号/规则断言（如 `__all__` 导出、
标记形状）与真实装配证明（构建 composition root 容器并断言 fail-closed）分文件
维护，符号断言不得替代装配证明；装配证明留在低成本入口（unit）执行，不推入
串行树抬高其执行成本。迁移必须附原保障→迁移后保障逐例映射，且执行频率不降低
（fast 车道收集数前后一致；新 integration 树须按串行审计形态登记解除，否则
迁移件会掉出 fast 车道）。已迁组：data specimen store（PIT coverage 区间/
knowable_from/allowed_uses/内容寻址不可变）、execution paper 会话库恢复组
（CAS/revision/幂等重放/防篡改 fail-closed）；backend 组合证明按接缝拆为
symbol-rules 与 assembly 两文件。

**等待治理（#348）**：删除固定等待须有同步合同证据——SDK 源码级核实等待是死等待
（如 `InMemoryMetricReader.get_metrics_data()` 在读取点同步 `collect()`，无后台
线程，读后即得）；仍需等待的行为用实际条件加有限超时表达，不扩大超时掩盖失败。
等待治理收益只报实测墙钟（≥5 组配对对照的中位数），不得以声明 sleep 时长之和
充当墙钟收益。生产 OTLP 路径不得指向真实端点：连接被拒会触发 OTLP HTTP
exporter 内建指数退避重试（约 15s/次 shutdown），基线里该成本被"provider 泄漏到
进程退出、从不 shutdown"掩盖——observability 树用本地 `_OtlpHttpSink`（真实
POST 往返 + 200 应答）同时获得确定性与真实传输断言。

**observability 树状态恢复步骤（#348）**：conftest autouse fixture 在每例前后各
执行一次 `reset_for_testing()`（只在测试前重置会把树内末例的脏状态泄漏给同进程
后续 owner 的用例）；OTel API 的 provider 全局是 once-only 写且无公开撤销入口，
teardown 按快照恢复 `_TRACER_PROVIDER`/`_METER_PROVIDER`、各自 `Once._done`
及 metrics proxy 绑定态——走 SDK 私有符号，版本由 uv.lock 钉住，符号漂移会在
teardown 响亮失败。纯配置字段合同与真实 SDK 接缝按用例区分，不按整文件归类：

| 用例组 | 判定 |
| --- | --- |
| 纯配置字段合同（原 integration 的 `TestPresetConfig`/`TestRuntimeFlags`，12 例） | 无 SDK 装配，并入 `tests/unit/observability/test_config_unit.py`：9 例与 unit 等价删除、3 例 preset 的 `pytest_running` 断言并入 unit 版本、1 例独有迁移 |
| configure/setup、tracing span、logging 文件输出、init/shutdown | 真实 SDK 接缝，保留 integration |
| `_resolve_log_dir`（4 例） | 文件系统契约（XDG/cwd/tmp），无 SDK 装配，保留 integration |

**fast 车道按资源/旅程选择，不按层级**：表达式（`not slow and not serial and not
e2e and not snapshot and not sandbox_live and not capacity`）单源维护于
`tooling/quality/test_selection.py`，`scripts/test.py --fast` 消费同一常量——低成本、
可并行的真实集成测试可进入快速反馈；`--unit`/`--integration` 车道仍按层级选。
harness 合并 fast 调用的 per-owner 非空证明自 #317-C 起由该次运行的 junit 证据承担
（替代旧收集探针，见「按风险验证」一节）。

导入期替换与全局 fixture 的隔离约定：

- conftest **不得在模块级替换全局符号**（如 `prefect.flows.flow`）——合并入口下
  会泄漏进其他 owner 的导入。作用域化的导入期替换经 layering 插件的
  `register_import_bracket(scope, apply, restore)` 注册，仅在本树模块导入期间生效
  （backend unit 的 Prefect mock 即此形态，见 `ditto_apps.prefect_mock`）。
- 跨 owner 全局状态的 autouse fixture（如 observability 初始化）必须在 teardown
  恢复，使全仓/分片等共享进程入口不把状态泄漏给后续 owner。
- 近端 conftest 的 `sys.path.insert` 仅允许暴露**本目录**测试 helper，不得共享命名。

tooling 测试在默认 testpaths 之外：本地统一经 `task tooling-test`（含
`tooling/release/tests`），CI 的 release-policy job 亦执行 release 测试。一致性
证据入口：`task entry-consistency` 逐 nodeid 比较各入口标记集，漂移即 exit 1。

测试应确定、隔离且可并行。时间、随机数、外部 I/O 与 source snapshot 必须显式控制；失败后清理临时状态。

`scripts/test.py` 在启动 pytest 前为子进程固定 `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`，
覆盖收集阶段、xdist worker 和测试创建的子进程。显式真实数据验收通过独立入口运行，
不得依赖默认自动化测试读取个人钥匙串。

Registry 配置测试通过近端 `conftest.py` 临时安装现有 keyring 包的 null backend，
保留真实 ConfigProvider 装配，但不读取宿主钥匙串；每项测试结束恢复原 backend。
测试具体密钥行为时显式注入固定值，生产密钥读取和显式真实数据 E2E 不受此 fixture 影响。

本机完整验收通过根 `task check` 编排；不要另起同一套后端和 Web 门禁并行抢占
资源。集中出现交互测试超时时，先单独复现并排查资源争用，不直接增加超时或重试次数。

## 测试时长治理

单条用例时长预算：单测 <0.5s、集成 <5s（与 `task analyze-slow-tests` 同阈值）。预算是
**分类阈值与治理输入，不是合并门**（#340）：CI 的 `slow_test_gate --report` 消费同次
执行的分片 junit 证据，对新用例超标只报告不打标阻断；真实功能失败、挂死超时和明确产品
性能合同仍由分片/capacity/PIT 各自阻断。超标新用例与存量一起按打标治理票和等价重复清单
流程处置（#321）。fast 车道（`task test -- --fast`）另带 **10s/用例硬顶超时**兜住异常
用例（挂死/失控）——硬顶只杀真异常，0.5s 附近的边界人群由治理清单处置而非本地误杀。

时长证据常驻：pytest addopts 自带 `--durations=10`；治理入口
`task analyze-slow-tests`（覆盖全部测试根，已打 `slow`/`capacity` 标记的用例走慢车道不计入；
未打标的超标用例——含存量——使命令 exit 1，即待治理清单，按本节与 #321 流程处置）。pytest-timeout 全局 600s 兜底防挂死（pyproject `timeout`），
合法慢测试靠标记进慢车道表达，不以调大全局超时掩盖；疑似挂死先单独复现并排查资源
争用，不直接加超时或重试。

测试必须可并行：默认 `-n auto --dist loadfile`（同文件聚组），禁止用例间顺序依赖；
跨文件互斥的用例打 `serial`——该标记在 CI 分片的两车道结构中生效，本地复现串行用
`-n 0`（如 `uv run --no-sync pytest <path> -q -n 0`）。SQLite 测试按 worker 隔离：用 `worker_id` fixture 加 `tmp_path` 给每 worker
（必要时每用例）独立 DB 文件，禁止多 worker 共享同一 DB 路径。贵重一次性构建的
fixture 升 `scope="session"`（xdist 下为每 worker 一次），可变状态保持 function 级。

固定 sleep 是 flake 工厂：等待外部条件用条件轮询加总超时，不写裸等待。Polars 自带
线程池，与 xdist 叠加时留意超订阅：疑似时实测 worker 数与 `POLARS_MAX_THREADS`
组合，不凭感觉调整。

阶梯档级耗时预算与实测基线见[工具链文档](toolchain.md)的 CI 时长基线小节（#318）。

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

仅测试 diff 仍需 Ruff format-check/lint 和测试类型检查；conftest/helper/fixture 变更
作用于所属 owner 的整棵测试树，不直接收集单个文件。普通生产改动（单包或跨包）运行
**影响范围**各包测试——改动 owner 的声明生产反向闭包 ∪ 测试使用关系，由共享事实层
`tooling/agent_harness/impact_scope.py` 推导（#338/#317-C）——与共享的 Ruff/类型检查；
合并 fast 调用以该次运行的 junit 证据证明每个 scope owner 有已执行用例，缺证据即升级
`task check`。契约、依赖、架构或工具链改动运行 `task check`。远端 CI 是权威合并门
（后端完整 coverage 不因本地闭包裁剪），本地通过不替代 CI。

## 覆盖率与证据

覆盖率阈值以 [.github/codecov.yml](../../.github/codecov.yml) 和 Web 的
[vitest.config.ts](../../apps/web/vitest.config.ts) 为准，不在说明中复制数值。覆盖率不是新增无意义断言的目标。优先证明正常路径、边界、失败恢复、PIT 隔离和关键状态转换。

最终报告只列实际运行过的命令。平台、依赖或外部凭证使检查无法运行时，说明精确原因和剩余风险。

## 可选历史质量比较

普通审视报告事实、影响和建议。仅在明确要求历史可比评分时，显式选择 rubric 与范围并记录版本、基线提交和测量覆盖。
旧口径定义固定为 [legacy-v1（688386be）](https://github.com/cosmos-arc/ditto/tree/688386be200af5fd8d92e138575f55f283b5dd05/.agents/skills/ditto-quality-eval)，包括分项表、权重、封顶规则及报告结构；它仅用于复现历史报告，不是当前 CI 或编码规则。
按该口径 pass/warning/fail 分别取 100%/60%/0%，not_measured 从分母排除并披露缺口；仅在同口径、同范围下比较。每个基线命令采集一次，不把静态政策 fixture 当作模型行为证据。
