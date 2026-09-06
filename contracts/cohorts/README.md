# Release cohort compatibility policy

`compatibility-policy.json` 是 Web/API 正式运行兼容矩阵的根事实源，
`compatibility-policy.sha256` 固定其原始字节。两者必须同时更新并通过：

```bash
task cohort-compatibility-check
```

policy 只允许一个动态 `current` build slot 和至多一个真实 `previous` cohort。
`current.source=web_build` 是必要的非自引用设计：包含 policy 的提交无法在同一
policy 中预先写入自身 Git SHA。Vite 构建时使用 product version、完整 40 位
Git SHA、`v1` 和 OpenAPI 64 位 SHA-256 将该 slot 物化，并把 policy SHA-256
及 current/previous 的完整 exact identities 一并嵌入 Web 制品。

正式运行只接受以下组合：

- Web 与 backend identity 完全相同：正常通过；
- current/previous 是 policy 明列的两个 exact identities：通过并显示明确的
  rollback/rolling-upgrade warning；
- version、Git SHA、API contract version 或 contract SHA-256 任一其它组合：
  fail closed。

这里不采用 product SemVer major 或 API major 推断兼容性。开发模式仍以 Web
当前 build identity 为比较基准并显示 drift warning。

双向 current↔previous 判定由合成测试覆盖，但 immutable 的 previous Web 制品
不可能预知未来 current identity。默认发布顺序因此是先部署 current Web、再部署
current backend；回滚顺序相反。若未来必须允许任意顺序的“旧 Web + 新 backend”，
需要另行设计受签名的 runtime policy 或可追溯的 transition Web 制品，不能用
same-major wildcard 伪装成已验证兼容。

## 登记上一 release

当前还没有可验证的 prior release，因此 checked-in `previous` 必须为空。每次
正式发布会把该次经过 attestation 的 `release-cohort.json` 转成：

```text
dist/next-cohort-policy/compatibility-policy.json
dist/next-cohort-policy/compatibility-policy.sha256
```

准备下一 release 时，只能使用可信 release 下载的 manifest，通过命令生成并
评审变更：

```bash
python -m tooling.release.compatibility_policy register-previous \
  --release-manifest /absolute/path/to/release-cohort.json
```

命令会复算 `cohort_id`、验证 schema、SemVer、完整 Git/OpenAPI hash、`v1`，
再以 canonical JSON 和匹配 sidecar 原子写入根 policy。不得手工添加推测的历史
identity。
