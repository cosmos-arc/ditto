# 旧 SHA 发布资格恢复（#352）

适用场景：要发布一个 main 已前进的旧提交（例如回滚性热修复重打
旧版本），而该 SHA 的 main `event=push` CI 运行已失败、被取消或
产物过期。发布门（release.yml "Verify release source provenance"）
要求：目标 SHA 是 main 祖先 + 该 SHA 的 ci.yml `event=push` 且
`head_branch=main` 的**最新**运行结论为 success——workflow_dispatch
与 PR 事件运行不参与判定，不能冒充。

## 恢复流程

1. 找到该 SHA 在 **main 分支**上的精确 push 运行（同 SHA 可能在其他
   分支也有 push 运行，重跑它无法满足发布门）：
   `gh api "repos/cosmos-arc/ditto/actions/workflows/ci.yml/runs?head_sha=<SHA>&event=push&branch=main" --jq '.workflow_runs[0].id'`
2. **仅当该 push 运行结论不是 success 时**才需要恢复——发布门只看
   结论，不看产物保留期：成功的旧 run 即使产物过期也直接放行，不要
   为过期产物重跑成功运行。
3. 前置检查：确认当前没有**任何活跃态**的 CI 工作流 run——
   `in_progress`、`queued`、`pending`、`requested`、`waiting` 逐个
   查询 `gh run list --workflow CI --branch main --status <状态>` 均
   为空（注意不能只看 `--limit 1` 的最新 run，可能是其他工作流的
   已完成 run）；ci.yml 的 concurrency 组 `ci-CI-refs/heads/main` 带
   cancel-in-progress，恢复性重跑若与普通 main push 重叠会互相取消；
   错峰执行。
4. 原地重跑保持 event=push 身份（不新开 dispatch）。先处理冲突产物：
   任何以 `if: always()` 上传的产物（tested-commit、backend-shard-*、
   backend-coverage-* 等）在同 run_id 重跑对应 job 时会与 v4 不可变
   语义冲突——重跑前删除将被重跑 job 再度上传的产物：
   `gh api repos/cosmos-arc/ditto/actions/runs/<run-id>/artifacts` 列出，
   `gh api -X DELETE repos/cosmos-arc/ditto/actions/artifacts/<id>` 删除。
   按原结论分派：
   - failure / timed_out：默认 `gh run rerun <run-id> --failed`
     只重跑未成功 job；其中已上传过产物的失败 job（如失败 shard 的
     backend-shard-*）须先按上段删除其产物，否则重跑在同一上传步
     反复失败。
   - stale：job 也以 stale 结束而非 failure，`--failed` 无可选 job——
     与 startup_failure 同样走整跑重试+先删全部产物。
   - startup_failure：该 run 可能没有任何 job，`--failed` 无从重跑——
     整跑重试 `gh run rerun <run-id>`，并按取消态同样先删全部产物。
   - cancelled：取消态没有 failed job 可重跑，整跑重试
     `gh run rerun <run-id>`——整跑重执行**所有** job，取消前任何
     job 已上传的产物（tested-commit、web-dist、backend-shard-* 等）
     都会撞名，**必须先删除该 run 的全部产物**再整跑（不删则上传步
     必失败，无法"接受退化"绕过）。
   - action_required：不是重跑问题——先处理待审批（环境保护/审批），
     再按上述分派。
   重跑产生同 run_id 的新 attempt，结论取最新 attempt。
5. 重跑成功后按常规发布流程触发 release；发布门按上面的规则放行。

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

机检命令（--since 取证据机制**上线时间戳**——整日会把上线前的同日 run 计为 unexplained）：

```
GH_TOKEN=... python -m tooling.agent_harness.main_evidence observe \
  --limit 30 --since 2026-09-29T13:44
```

样本不足不切换；观察期证据变化后重取。切换落地时同步更新
ADR0015 与本文件。
