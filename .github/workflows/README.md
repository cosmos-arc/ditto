# GitHub Actions governance

Ditto 将 CI、安全与发布证据分成三个职责明确的工作流。所有第三方 Action 使用完整 commit SHA，工作流默认只有 `contents: read`；写权限只在 CodeQL 上传和发布 attestation 的 job 局部开放。

## Required checks

分支保护与 merge queue 只要求一个稳定名称：

- `CI / CI gate`

`ci.yml` 在 `pull_request`、`main` push 和 `merge_group` 上无条件启动以下十二个并行语义 job：

1. repository policy
2. backend format/lint
3. backend types
4. backend tests/coverage
5. architecture/agent harness
6. Web lint/types/tests/build
7. OpenAPI compatibility/generated types
8. supervised backend-Web system test
9. release cohort generator/evidence
10. container build/readiness smoke
11. macOS arm64 与 Windows x64 platform smoke
12. 可复用 security/supply-chain workflow

`ci-gate` 只接受十二个 `success`；`failure`、`cancelled` 和 `skipped` 都会失败。工作流不使用顶层 `paths` 或条件跳过，因此 required check 不会因改动路径而消失。

`security.yml` 由 `ci.yml` 通过 `workflow_call` 调用，并保留周度 schedule：

- CodeQL：Python 与 JavaScript/TypeScript matrix；
- Gitleaks：当前规则集与已验证兼容规则集双重完整历史扫描；兼容扫描另有合成 GitHub PAT 哨兵，避免扫描器“运行成功但规则失效”；所有历史假阳性逐 finding fingerprint 放行；
- OSV：递归扫描 Bun 等受支持的源码锁文件；
- container security：Trivy HIGH/CRITICAL fail-closed 与 SPDX JSON SBOM。

扫描器容器均固定 image digest。内部 `security-gate` 不接受 skipped，其结果再作为
`security-supply-chain` job 被唯一 `ci-gate` 汇总。
每周 schedule 另行运行根 `mutation-critical` Pixi 任务并上传
`build/mutation/mutmut-cicd-stats.json`；它不进入 PR 快速 required gate。

## Release cohort

`release.yml` 在 `vX.Y.Z` tag 或显式手动版本上构建 OCI archive，生成 SPDX SBOM 与 `release-cohort.json`，随后通过 GitHub artifact attestation 生成 provenance。工作流只上传制品，不自动部署或推送镜像。

本地验证 manifest：

```bash
pixi run -e dev python -m pytest tooling/release/tests -q -n 0
pixi run -e dev python -m tooling.release.cohort_manifest \
  --workspace-root . \
  --artifact contracts/openapi/v1.json \
  --artifact pixi.lock \
  --artifact bun.lock \
  --artifact dist/ditto-image.tar \
  --artifact dist/ditto-web.tar \
  --backend-artifact dist/ditto-image.tar \
  --web-artifact dist/ditto-web.tar \
  --product-version 0.1.0-dev \
  --git-sha "$(git rev-parse HEAD)" \
  --api-contract-version v1 \
  --api-contract-sha256 "$(sha256sum contracts/openapi/v1.json | cut -d ' ' -f 1)" \
  --generated-at 2026-09-04T00:00:00Z \
  --output dist/release-cohort.json
```

## Repository settings required outside Git

这些设置无法由仓库文件安全完成，必须在 GitHub 管理面配置：

- 启用 branch protection/ruleset，并把两个 gate 设为 required；
- 启用 merge queue，required checks 与 `merge_group` 保持一致；
- 启用 Code scanning；公开仓库可用，组织私有仓库需启用
  [GitHub Code Security](https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-code-scanning)；
- 启用 artifact attestations；私有或内部仓库需要
  [GitHub Enterprise Cloud](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)；
- 安装并授权 Renovate GitHub App，只保留 Renovate 一个依赖机器人；
- 配置 tag/release ruleset，限制 `v*` tag 创建权限；
- 如仓库属于组织，配置 Actions allowlist，仅允许已批准的 SHA-pinned Action。
