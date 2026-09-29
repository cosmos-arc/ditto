# 旧 SHA 发布资格恢复（#352）

适用场景：要发布一个 main 已前进的旧提交（例如回滚性热修复重打
旧版本），而该 SHA 的 main `event=push` CI 运行已失败、被取消或
产物过期。发布门（release.yml "Verify release source provenance"）
要求：目标 SHA 是 main 祖先 + 该 SHA 的 ci.yml `event=push` 且
`head_branch=main` 的**最新**运行结论为 success——workflow_dispatch
与 PR 事件运行不参与判定，不能冒充。

## 恢复流程

1. 找到该 SHA 的精确 push 运行：
   `gh api "repos/cosmos-arc/ditto/actions/workflows/ci.yml/runs?head_sha=<SHA>&event=push" --jq '.workflow_runs[0].id'`
2. **仅当该 push 运行结论不是 success 时**才需要恢复——发布门只看
   结论，不看产物保留期：成功的旧 run 即使产物过期也直接放行，不要
   为过期产物重跑成功运行。
3. 原地重跑保持 event=push 身份（不新开 dispatch）。按原结论分派：
   - 结论为 failure：默认 `gh run rerun <run-id> --failed` 只重跑失败
     job；`--failed` 不重跑原本成功的 job，tested-commit 产物不受
     影响。
   - 结论为 cancelled：取消态没有 failed job 可重跑，需整跑重试
     `gh run rerun <run-id>`——注意它会重新执行 repository-policy
     并再次上传 `tested-commit-<run_id>`，与 v4 产物不可变语义冲突
     （必要时先删旧产物或接受该次证据退化，退化为 push 全量验证仍
     安全）。
   重跑产生同 run_id 的新 attempt，结论取最新 attempt。
4. 重跑成功后按常规发布流程触发 release；发布门按上面的规则放行。

## 边界

- 不存在该 SHA 的成功 push 运行且无法重跑（例如运行被删除）时，
  该 SHA 无发布资格——以 dispatch/workflow_dispatch 新建的运行不是
  `event=push`，不满足门；不得放宽门的身份过滤。
- 没有成功真实发布证据时明确记录"未验收"，不擅自触发生产发布。
- 本流程不改变发布身份合同（精确 SHA、重建 Web/OCI、smoke、扫描、
  SBOM、checksum、attestation 仍由 release 流水线强制）。

## 影子观察与最终开关（平台职责）

main push 的收窄选择（#351）已有三腿机器证据核验。进一步把
platform-smoke 从每次 push 移到"PR 原生 + 周度 cron"的最终开关，
须先完成影子观察：≥7 天、≥10 个不同候选 SHA 的 push run 证据全部
可解释（verified 有理由链、full-required 有明确原因）。

机检命令：

```
GH_TOKEN=... python -m tooling.agent_harness.main_evidence observe --limit 30
```

样本不足不切换；观察期证据变化后重取。切换落地时同步更新
ADR0015 与本文件。
