# 0011 - 分层验证与 CI 证明范围

**状态**：Accepted，2026-09-08 用户确认。补充 ADR 0010 的合并前完整验证取舍，不改变 Task/uv/Bun 所有权或 release cohort 合同。

普通 PR 采用可解释的粗粒度检查范围：纯 Web 保留 Web、契约和真实双栈验收；普通后端保留全后端测试、契约、真实双栈和平台敏感行为。根工具链、锁、公共契约、安全/发布配置、高风险业务与未知范围运行全套。main、merge queue、定期与正式发布保留完整证明；普通 PR 10–15 分钟是测量目标，不能通过降低阈值或吞掉失败实现。

本地日常验证以当前包测试与静态检查为主，跨包和高风险运行完整入口。CI 是权威合并门；本地成功、缓存命中、报告上传成功都不能替代当前提交的测试证明。

后端可在隔离 runner 分片，标记 serial 的用例在各自 runner 单进程执行。合并前必须验证所有分片的提交、相同完整收集清单、无遗漏的确定性分配和覆盖率数据摘要，再按合并结果执行原有全局、敏感包与 changed-code 阈值。选择器和汇总门对未知、失败、取消、缺失与错误跳过均 fail closed。

相较每次运行两栈全部检查，此决策缩短普通变更反馈；代价是必须维护分类器反例及完整回归。相较细粒度动态依赖推断，目前保留全后端测试以降低漏测风险。验证结果不作跨提交缓存，复用制品必须验证当前提交与契约身份。

2026-09-28 补充（#340，[验证体系决议](https://github.com/cosmos-arc/ditto/issues/339#issuecomment-5861717841) 阶段 A）：本地 pre-push 只保留推送身份/范围核对与显式验证提示，pytest、全量类型、PIT 与 system 退出同步 push 路径；同一阶梯由送审前显式入口 `task verify-push` 执行，缺历史与模式异常在该计划内 fail-closed 为全量门。通用 0.5s/5s 时长阈值转为消费同次分片 junit 证据的报告，不再作为合并阻断；功能失败、挂死超时与产品性能合同仍由分片/capacity/PIT 阻断。轻量 push 通过不等于已通过完整验证，PR CI 权威门与 main 证据要求不变。

2026-09-28 补充（#330 阶段 B1，同决议）：目录到测试层级的映射收敛为单一规则（`tooling/quality/pytest_layering.py`，经仓库根 conftest 注册，单文件/owner/全仓/分片入口一致），近端 conftest 不再修改外国 owner 的标记（旧路径钩子移除）；`integration` 目录附带 `serial` 的 blanket 资源策略保留至串行审计（#226）逐组解除。fast 车道表达式去层级化（按 slow/serial/e2e/snapshot/sandbox_live/capacity 资源维度单源选择），低成本真实集成可进入快速反馈；owner 覆盖探针消费同一常量。导入期全局替换（backend unit 的 Prefect mock）改为经 layering 插件注册的树作用域 bracket，跨 owner 全局 autouse 状态在 teardown 恢复。入口一致性以 `task entry-consistency` 逐 nodeid 核验；tooling 测试（含 tooling/release）统一进 `task tooling-test`。
