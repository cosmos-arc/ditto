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
11. macOS arm64 与 Windows x64 platform smoke（Windows 除双栈类型检查外，
    运行代表性的 kernel/API/CLI 单测、Web 契约/运行配置单测，以及真实 loopback
    API 的 `/healthz`、`/readyz` 与 release cohort 身份验收；API 使用一次性
    config/state/cache roots 并在成功或失败后回收完整进程树）
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

`release.yml` 在 `vX.Y.Z` tag 或显式手动版本上构建并验证 Docker image tar，生成 SPDX SBOM 与 `release-cohort.json`，随后通过 GitHub artifact attestation 生成 provenance。发布 SHA 必须位于 `main`，并且该精确 SHA 已有成功的 `ci.yml` 运行；最终 release image 还会真实启动、通过 `/readyz` 并接受 Trivy HIGH/CRITICAL 扫描。Tag 运行会把 cohort 作为长期 GitHub Release 附件发布；手动运行只保留 90 天 Actions artifact。工作流不部署服务，也不推送容器 registry。

`ditto-release-cohort.tar` 是保持目录层级的可移植交付封套。它包含 backend/Web
制品、SBOM、`release-inputs/`、manifest、下一 cohort 的兼容策略候选，以及
`release-tools/` 下与该 release 同一提交的零第三方依赖 verifier。manifest 对所有
内层制品和 verifier 文件做哈希绑定；tar 本身刻意不进入 manifest，避免递归
self-reference，而是由外层 `SHA256SUMS`、attestation、Actions artifact 和 GitHub
Release 绑定。tar 成员按路径排序，使用固定 commit timestamp、`0644`、uid/gid 0
和空 owner 名；构建器在产出后重新打开并拒绝符号链接、非普通文件、路径逃逸和
不确定元数据。

离线接收方下载 `ditto-release-cohort.tar`、同次发布的
`ditto-release-cohort.attestation.json` 与 `SHA256SUMS`。可信根不能从同一个 release
附件获得；应在一台可信的联网机器上直接从 GitHub/Sigstore 获取并通过独立介质导入
离线环境：

```bash
gh attestation trusted-root > /trusted/github-attestation-root.jsonl
```

在离线环境中先验证外层 Sigstore bundle，并把仓库、签名 workflow、预期 Git SHA
和 tag ref 全部锁定；只有成功后才能信任 checksum、解包或执行封套内 verifier：

```bash
expected_git_sha="<expected-Git-SHA>"
release_tag="<release-tag>"
gh attestation verify ditto-release-cohort.tar \
  --bundle ditto-release-cohort.attestation.json \
  --custom-trusted-root /trusted/github-attestation-root.jsonl \
  --repo cosmos-arc/ditto \
  --signer-workflow github.com/cosmos-arc/ditto/.github/workflows/release.yml \
  --source-digest "$expected_git_sha" \
  --source-ref "refs/tags/$release_tag" \
  --deny-self-hosted-runners
sha256sum --check --ignore-missing SHA256SUMS
mkdir -p ditto-release-cohort
tar -xf ditto-release-cohort.tar -C ditto-release-cohort
cd ditto-release-cohort
python3 release-tools/verify-cohort.py \
  --workspace-root . \
  --manifest release-cohort.json
```

严格 verifier 重新校验 exact schema、canonical JSON、`cohort_id`、路径
containment、普通文件/无符号链接、大小、固定 MIME、SHA-256、backend/Web 摘要
记录、完整 verifier runtime，以及 versioned OpenAPI digest 绑定。兼容策略注册
同样先调用这套 verifier；manifest 位于 cohort 根时可省略 `--workspace-root`，位于
子目录时必须显式传入实际 cohort 根，不能只凭 manifest 声明登记历史 release。

本地验证 manifest（须先通过 artifact gate 生成真实 backend/Web tar 与对应的
canonical SPDX SBOM；Web SBOM 必须绑定最终 tar 的 SHA-256，不接受空包列表或占位文件）：

```bash
pixi run -e dev python -m pytest tooling/release/tests -q -n 0
mkdir -p dist/release-inputs/contracts/openapi
mkdir -p dist/release-inputs/contracts/cohorts
install -m 0644 contracts/openapi/v1.json dist/release-inputs/contracts/openapi/v1.json
install -m 0644 contracts/cohorts/compatibility-policy.json dist/release-inputs/contracts/cohorts/compatibility-policy.json
install -m 0644 contracts/cohorts/compatibility-policy.sha256 dist/release-inputs/contracts/cohorts/compatibility-policy.sha256
install -m 0644 pixi.lock dist/release-inputs/pixi.lock
install -m 0644 bun.lock dist/release-inputs/bun.lock
pixi run -e dev python -m tooling.release.cohort_bundle stage-tools \
  --source-root . \
  --workspace-root dist
pixi run -e dev python -m tooling.release.cohort_manifest \
  --workspace-root dist \
  --artifact release-inputs/contracts/openapi/v1.json \
  --artifact release-inputs/contracts/cohorts/compatibility-policy.json \
  --artifact release-inputs/contracts/cohorts/compatibility-policy.sha256 \
  --artifact release-inputs/pixi.lock \
  --artifact release-inputs/bun.lock \
  --artifact release-tools/tooling/__init__.py \
  --artifact release-tools/tooling/release/__init__.py \
  --artifact release-tools/tooling/release/cohort_manifest.py \
  --artifact release-tools/tooling/release/cohort_verify.py \
  --artifact release-tools/verify-cohort.py \
  --artifact ditto-image.tar \
  --artifact ditto-web.tar \
  --artifact ditto-backend.spdx.json \
  --artifact ditto-web.spdx.json \
  --backend-artifact ditto-image.tar \
  --web-artifact ditto-web.tar \
  --product-version 0.1.0-dev \
  --git-sha "$(git rev-parse HEAD)" \
  --api-contract-version v1 \
  --api-contract-sha256 "$(sha256sum dist/release-inputs/contracts/openapi/v1.json | cut -d ' ' -f 1)" \
  --generated-at 2026-09-04T00:00:00Z \
  --output release-cohort.json
pixi run -e dev python -m tooling.release.cohort_verify \
  --workspace-root dist \
  --manifest release-cohort.json
pixi run -e dev python -m tooling.release.compatibility_policy register-previous \
  --workspace-root dist \
  --release-manifest dist/release-cohort.json \
  --output-policy dist/next-cohort-policy/compatibility-policy.json \
  --output-digest dist/next-cohort-policy/compatibility-policy.sha256
pixi run -e dev python -m tooling.release.cohort_bundle create \
  --workspace-root dist \
  --manifest release-cohort.json \
  --include next-cohort-policy/compatibility-policy.json \
  --include next-cohort-policy/compatibility-policy.sha256 \
  --output ditto-release-cohort.tar \
  --source-date-epoch "$(git show -s --format=%ct HEAD)"
```

根 `pixi run -e dev artifact-gate` 在读取 `HEAD` 并给制品写入 `git_sha` 前，会检查
staged、unstaged tracked 以及所有未被 ignore 的 untracked 文件；任何 dirty source
都会 fail closed。被 ignore 的构建输出不影响 provenance 检查。

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
