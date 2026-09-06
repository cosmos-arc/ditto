# 覆盖率子进程超时诊断（2026-09-06）

诊断起点：`360d8d52`，工作目录 `ditto-harness-simplification`。

**结论：本轮未复现，根因未确认，没有实施代码修复。** 原始 `backend-coverage` 入口已完整通过，
但一次全量成功和多次重放成功不能证明间歇问题已消失。10 秒 / 90 秒超时、覆盖率 source、
branch、subprocess patch、阈值及默认 worker 策略均未修改。

## 原始症状

前轮完整 CI 的同一个 `gw7` 上，以下两项先后超时：

- `test_wrapper_isolates_keyring_before_collection_and_in_workers`：10 秒；stderr 已打印包装器将运行的 pytest 命令。
- `test_run_eod_never_enters_prefect_engine_in_real_import_process`：90 秒；子进程 stdout/stderr 为空。

原日志只有父进程的 `TimeoutExpired`，没有超时时刻的子进程堆栈。不能据此确定它卡在导入、
业务调用、覆盖率保存或其他阶段，也不能把“资源争用”直接认定为根因。

## 实际重放

所有缩小重放保留完整 coverage source 和 subprocess patch，使用独立 coverage 数据文件。
测试顺序来自原日志中的实际 worker 完成记录，保留带空格的参数化 node ID。
没有降低超时、注入等待、屏蔽覆盖率或修改产品源码来制造失败。

| 重放条件 | 结果 | pytest 耗时 |
| --- | --- | --- |
| 两个目标文件，完整 coverage，串行 | 11 通过 | 14.08 秒 |
| 原 worker 到首个目标的顺序，串行 | 917 通过 | 49.77 秒 |
| 原 worker 到两个目标的顺序，真实单 worker | 933 通过 | 62.40 秒 |
| 全库收集，仅执行两个目标，单 worker | 2 通过 | 38.59 秒 |
| 全库收集，仅执行两个目标，八 worker | 2 通过 | 66.23 秒 |
| 全库收集并重放原 worker 的完整前序，单 worker | 933 通过 | 87.97 秒 |
| 原始 `backend-coverage`，默认并行与输出位置 | 16,469 通过、73 跳过 | 729.02 秒 |
| 八 worker 各自执行上述 933 项序列（`--dist=each`） | 7,464 通过 | 236.54 秒 |

最后一轮中，两目标各通过八次；Prefect 目标最慢 21.12 秒，仍低于 90 秒。
测试顺序、全库收集和并发负载分别及组合重放均未得到 RED，因此没有进入根因假设及修复阶段。

完整入口实际命令：

```bash
COVERAGE_BASE_REF=688386be200af5fd8d92e138575f55f283b5dd05 pixi run -e dev backend-coverage
```

该命令退出 0，wall time 731.35 秒；完整覆盖率仍为 **89.41%**，原有阈值全部满足。
这更新了后端覆盖率入口的验证证据，不改变安全漏洞、远程 CI/Windows 验收等独立限制。

## 证据与后续所需信息

原始日志：`/tmp/ditto-tickets-80/full-ci.log`。
本轮日志、原 worker node 列表及仅用于诊断的顺序重放插件保存在
`/tmp/ditto-timeout-diagnosis/`；旧 coverage 产物已备份到其 `previous-coverage/` 子目录。
该目录明确属于临时调试材料，不接入 CI 或日常任务，也不作为稳定回归测试。
没有留下产品代码调试日志，没有创建推测性的回归断言。

继续定位需要下一次失败时的 **worker / 子进程进程树与即时堆栈**，以及对应完整命令、日志和运行环境；
或者提供可重复触发的 runner/环境。事后只有 `TimeoutExpired` 不能替代这些证据。
应先捕获具体阻塞位置，再构造能稳定拒绝该问题的最小回归测试；目前不能将此问题标记为已修复。
