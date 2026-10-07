# GitHub Actions governance

Ditto 将 CI、安全与发布证据分成职责明确的工作流，并以双层门禁组织（#538）。所有第三方
Action 使用完整 commit SHA，工作流默认只有 `contents: read`；写权限只在 CodeQL 上传、
merge freeze 变量与发布 attestation 的 job 局部开放。

## 双层门禁（#538）

- **`ci.yml` 快速门（阻断合并）**：repository 策略选择、backend 质量/类型、无过滤
  marker 收集（`marker-dump`）、10 分片重切、coverage 合并与 90% 地板、PIT marker 与
  OpenAPI conformance 红线证据、api-contract、架构/harness、release 策略、Web 质量/
  构建、安全快检（gitleaks+OSV）。快速门目标 p50 ≤5 分钟（#501）：目标而非门，
  超时如实报告不判失败。
- **`deep-ci.yml` 深度层（异步，不阻断当前 PR）**：平台双栈冒烟（macOS 双门并行）、
  容器烟测、安全全量（CodeQL）、系统 E2E、容量慢车道、Web 原型覆盖。深度层自含
  Web 构建，不跨工作流复用工件。周度 schedule（周一 01:11 UTC）强制全量，深度层
  不会被路径选择永久跳过。

### Merge freeze（深度层兜底）

`deep-ci.yml` 在 main（push/周度/手动 dispatch）上以 `freeze-manager` 维护仓库变量
`DEEP_LAYER_MERGE_FREEZE`：深度层红 → 写入变量（值记录红车道与来源 run），此时
`ci.yml` 的 `ci-gate` 对所有 PR 拒绝通过（变量 API 意外状态亦判冻结，fail-closed；
token 无变量能力时降级告警放行——此时写侧同样不可用，机制整体离线）；解冻条件是
冻结值记录的全部红车道在本轮实际跑绿（普通证据链 push 只跑 platform-smoke，不得
清掉其他车道的冻结——红要被解决，不是被 outranked）。写/删失败重试后 loud 失败。
重跑历史红 run 会以其原 SHA 重写冻结，解冻以 main 当前树的 dispatch/周度复跑为准。
冻结期间的修复 PR 经维护者确认其 PR 深度层结果后由维护者手动合并（仓库既有
`--admin` 通道），合入后 main 深度层复绿自动解冻。变量读写优先 `DITTO_AGENT_PAT`。

### 事件驱动通知（`notify.yml`）

`pull_request_review`（submitted）与 `workflow_run`（CI/Deep CI completed）事件被
`notify.yml` 转成机器可读 JSON（run 摘要与日志）；配置 `DITTO_AGENT_PAT` secret 后
额外发送 `repository_dispatch`（`ditto-loop-event`），PAT 触发绕开 GITHUB_TOKEN 事件
防递归，供 agent 侧自动化消费。宿主会话轮询仍是本地兜底。PR 级 concurrency 组以
新 push 取消旧 SHA 的运行，不浪费 runner 与注意力。

## Required checks

分支保护只要求一个稳定名称（ruleset 无 merge queue 规则，未启用 merge queue）：

- `CI gate`

选择层在 `tooling/agent_harness/ci.py`（代码单一权威，不引入 YAML policy 层），输出
`required`（快速门 job）与 `deep`（深度层 job）两组。主分支 push 沿用 PR 证据链核验
（#351）而非重跑全量。普通文档保留轻量路径，skill 文本/镜像增加
结构检查；根配置、共享工具、契约与未知范围 fail-closed 到全量双层。

`ci-gate`/`deep-gate` 要求各自选中的检查全部成功，不适用的检查允许跳过；失败、取消、
缺失结果或错误跳过均不能通过。快速门的红线保障（PIT marker、OpenAPI conformance、
coverage 地板、gitleaks/OSV）合并前不变。

`security.yml` 由两个工作流通过 `workflow_call` 调用：

- 快速门：`full-analysis=false` → gitleaks 完整历史扫描（digest-pinned，逐 finding
  fingerprint 放行；本地增量由 pre-commit gitleaks hook 覆盖）+ OSV 递归锁文件扫描；
- 深度层：`full-analysis=true, skip-quick=true` → CodeQL（Python、JavaScript/
  TypeScript、Actions matrix，本地分析+证据工件+Code Scanning 上传）；
- 周度：`skip-quick=false` 全量强制，另含文档链接检查（docs-links）。

扫描器容器均固定 image digest。`security-gate` 按所选安全范围区分不适用与失败。

## Turborepo 控制面（#526/#538）

根 `turbo.json` 是任务图/缓存/affected 的图事实源（`experimentalPythonWorkspaces` +
`experimentalTaskCommand`，turbo 精确 pin `2.11.7` + `bun.lock` 锁定，升级需显式同步
两处）。根 Taskfile 是零改动 facade：`task` 入口与本地验证阶梯保持不变，全退役待迁移
实测后另裁。turbo 对未知路径 affected=0 是结构性 fail-open，验证范围选择的 fail-closed
兜底由 `tooling/agent_harness`（`classify_diff`/根门路径）承担；迁移验收比较器：

```bash
uv run --no-sync python -m tooling.agent_harness.impact_scope turbo-compare \
  --base <sha> --head <sha>
```

对历史 base/head 回放并断言 turbo 选择 ∪ wrapper 升级 ⊇ 策略闭包的单调性。本地缓存
一律 `--cache-dir`（比较器用 `.turbo-local/cache`，已忽略入库），不得写默认共享
worktree 缓存污染主仓。

## Release artifacts

`release.yml` 在 `vX.Y.Z` tag 或显式手动版本上构建并验证最小发布集：backend
Docker image tar（distroless 基座，真实启动并通过 `/readyz` 与身份回读）、
Web 静态制品 tar、各一份 SPDX SBOM、单次 Trivy HIGH/CRITICAL 扫描、
`SHA256SUMS` 与 GitHub 原生 artifact attestation。发布 SHA 必须位于 `main`，
并且该精确 SHA 已有成功的 `ci.yml` 运行。Tag 运行把上述制品作为长期 GitHub
Release 附件发布；手动运行只保留 90 天 Actions artifact。工作流不部署服务，
也不推送容器 registry。

cohort manifest/自验证封套/离线 verifier/next-cohort 兼容策略注册链已于
2026-09 退役（issue #152）；回加条件为出现外部用户或需要离线分发的部署目标。

根 `task artifact-gate`（深度层 `container-smoke` 同一入口，自含 `task web-build`）
在读取 `HEAD` 并给制品写入 `git_sha` 前，会检查 staged、unstaged tracked 以及所有
未被 ignore 的 untracked 文件；任何 dirty source 都会 fail closed。被 ignore 的构建
输出不影响 provenance 检查。

## Repository settings required outside Git

这些设置无法由仓库文件安全完成，必须在 GitHub 管理面配置：

- 启用 branch protection/ruleset，并把唯一稳定检查 `CI gate` 设为 required
  （快速门即合并标准；深度层靠 merge freeze 兜底，不进 required checks）；
- 启用 Code scanning；公开仓库可用，组织私有仓库需启用
  [GitHub Code Security](https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-code-scanning)；
- 启用 artifact attestations；私有或内部仓库需要
  [GitHub Enterprise Cloud](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)；
- agent 侧事件消费启用时配置 `DITTO_AGENT_PAT` secret（可选，未配置时通知仅落
  run 摘要）；
- 安装并授权 Renovate GitHub App，只保留 Renovate 一个依赖机器人；
- 配置 tag/release ruleset，限制 `v*` tag 创建权限；
- 如仓库属于组织，配置 Actions allowlist，仅允许已批准的 SHA-pinned Action。
