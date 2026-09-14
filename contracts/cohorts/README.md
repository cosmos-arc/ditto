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

## 登记 previous release

release cohort 注册链已随 2026-09 的 release 简化退役（issue #152）；当前
checked-in `previous` 保持为空。若出现外部用户或需要回加发布链路，`previous`
只能手工登记有 attestation 凭证的真实 release identity，并以 canonical JSON
与匹配 sidecar 同步更新；不得添加推测的历史 identity。
