# GitHub Actions governance

Ditto 将 CI、安全与发布证据分成三个职责明确的工作流。所有第三方 Action 使用完整 commit SHA，工作流默认只有 `contents: read`；写权限只在 CodeQL 上传和发布 attestation 的 job 局部开放。

## Required checks

分支保护与 merge queue 只要求一个稳定名称：

- `CI / CI gate`

PR 按 `tooling/agent_harness/ci.py` 的共用 changed-scope 选择检查；主分支、
merge queue 与定期 CI 执行全量。普通文档保留轻量路径，skill 文本/镜像增加结构检查；
根配置、共享工具、契约与未知范围使用完整门禁。具体分工见
[Harness 验证规则](../../docs/engineering/agent-harness.md#本地与-ci-的验证分工)。

`ci-gate` 要求选中的检查全部成功，不适用的检查允许跳过；失败、取消、缺失结果或
错误跳过均不能通过。稳定 required check 始终存在，不因路径筛选消失。

`security.yml` 由 `ci.yml` 通过 `workflow_call` 调用，并保留周度 schedule：

- CodeQL：Python、JavaScript/TypeScript 与 Actions matrix；
- Gitleaks：单版本 digest-pinned 完整历史扫描；所有历史假阳性逐 finding fingerprint 放行；本地增量扫描由 pre-commit gitleaks hook 覆盖；
- OSV：递归扫描 Bun 等受支持的源码锁文件；
- container security：Trivy HIGH/CRITICAL fail-closed 与 SPDX JSON SBOM。

扫描器容器均固定 image digest。内部 `security-gate` 按所选安全范围区分不适用与失败，其结果再作为
`security-supply-chain` job 被唯一 `ci-gate` 汇总。

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

根 `task artifact-gate`（CI `container-smoke` 同一入口）在读取 `HEAD` 并给
制品写入 `git_sha` 前，会检查 staged、unstaged tracked 以及所有未被 ignore
的 untracked 文件；任何 dirty source 都会 fail closed。被 ignore 的构建输出
不影响 provenance 检查。

## Repository settings required outside Git

这些设置无法由仓库文件安全完成，必须在 GitHub 管理面配置：

- 启用 branch protection/ruleset，并把唯一稳定检查 `CI / CI gate` 设为 required；
- 启用 merge queue，required checks 与 `merge_group` 保持一致；
- 启用 Code scanning；公开仓库可用，组织私有仓库需启用
  [GitHub Code Security](https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-code-scanning)；
- 启用 artifact attestations；私有或内部仓库需要
  [GitHub Enterprise Cloud](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)；
- 安装并授权 Renovate GitHub App，只保留 Renovate 一个依赖机器人；
- 配置 tag/release ruleset，限制 `v*` tag 创建权限；
- 如仓库属于组织，配置 Actions allowlist，仅允许已批准的 SHA-pinned Action。
