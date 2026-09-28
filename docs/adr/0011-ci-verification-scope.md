# 0011 - 分层验证与 CI 证明范围

**状态**：Accepted，2026-09-08 用户确认。补充 ADR 0010 的合并前完整验证取舍，不改变 Task/uv/Bun 所有权或 release cohort 合同。

普通 PR 采用可解释的粗粒度检查范围：纯 Web 保留 Web、契约和真实双栈验收；普通后端保留全后端测试、契约、真实双栈和平台敏感行为。根工具链、锁、公共契约、安全/发布配置、高风险业务与未知范围运行全套。main、merge queue、定期与正式发布保留完整证明；普通 PR 10–15 分钟是测量目标，不能通过降低阈值或吞掉失败实现。

本地日常验证以当前包测试与静态检查为主，跨包和高风险运行完整入口。CI 是权威合并门；本地成功、缓存命中、报告上传成功都不能替代当前提交的测试证明。

后端可在隔离 runner 分片，标记 serial 的用例在各自 runner 单进程执行。合并前必须验证所有分片的提交、相同完整收集清单、无遗漏的确定性分配和覆盖率数据摘要，再按合并结果执行原有全局、敏感包与 changed-code 阈值。选择器和汇总门对未知、失败、取消、缺失与错误跳过均 fail closed。

相较每次运行两栈全部检查，此决策缩短普通变更反馈；代价是必须维护分类器反例及完整回归。本地范围选择自 #317-C 起采用包级影响闭包（见下），PR CI 的后端完整 coverage 集合不裁剪。验证结果不作跨提交缓存，复用制品必须验证当前提交与契约身份。

2026-09-28 补充（#340，[验证体系决议](https://github.com/cosmos-arc/ditto/issues/339#issuecomment-5861717841) 阶段 A）：本地 pre-push 只保留推送身份/范围核对与显式验证提示，pytest、全量类型、PIT 与 system 退出同步 push 路径；同一阶梯由送审前显式入口 `task verify-push` 执行，缺历史与模式异常在该计划内 fail-closed 为全量门。通用 0.5s/5s 时长阈值转为消费同次分片 junit 证据的报告，不再作为合并阻断；功能失败、挂死超时与产品性能合同仍由分片/capacity/PIT 阻断。轻量 push 通过不等于已通过完整验证，PR CI 权威门与 main 证据要求不变。

2026-09-28 补充（#330 阶段 B1，同决议）：目录到测试层级的映射收敛为单一规则（`tooling/quality/pytest_layering.py`，经仓库根 conftest 注册，单文件/owner/全仓/分片入口一致），近端 conftest 不再修改外国 owner 的标记（旧路径钩子移除）；`integration` 目录附带 `serial` 的 blanket 资源策略保留至串行审计（#226）逐组解除。fast 车道表达式去层级化（按 slow/serial/e2e/snapshot/sandbox_live/capacity 资源维度单源选择），低成本真实集成可进入快速反馈。导入期全局替换（backend unit 的 Prefect mock）改为经 layering 插件注册的树作用域 bracket，跨 owner 全局 autouse 状态在 teardown 恢复。入口一致性以 `task entry-consistency` 逐 nodeid 核验；tooling 测试（含 tooling/release）统一进 `task tooling-test`。

2026-09-28 补充（#317 阶段 C，依据 [影响范围决议 #338](https://github.com/cosmos-arc/ditto/issues/338#issuecomment-5861623313)）：本地后端范围选择从"直接 owner 直测"升级为共享影响事实层（`tooling/agent_harness/impact_scope.py`）——包级**声明生产反向闭包**（各 owner pyproject）∪ **测试使用关系**（AST 扫描哪些 owner 的测试 import 受影响生产代码；只加测试责任、不回灌生产传播）∪ 直接测试责任；非代码输入按路径归属扩大。清单不可解析、未映射 `ditto_*` 导入或直接 owner 无测试树时 fail-closed 全量；manifest 变化保持全量门（base/head 图并集的保守等价）。fast 合并调用的 per-owner 非空证明改由**该次运行的 junit 证据**承担（去掉独立预收集探针）。仓内测试钉住 #338 记录的闭包表与四族测试使用边，并核验生产跨包 import 不超出声明依赖；`python -m tooling.agent_harness.impact_scope report --base B --head H` 提供历史回放对照。PR CI 的后端完整 coverage（全 6 分片 + capacity + 全局阈值）不变，CI 不因本地闭包裁剪任何 job。
