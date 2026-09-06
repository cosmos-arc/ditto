# 安全结果与外部交接（2026-09-06）

来源为同日主分支 [CI 34007684137](https://github.com/cosmos-arc/ditto/actions/runs/34007684137)：
[CodeQL](https://github.com/cosmos-arc/ditto/actions/runs/34007684137/job/101417834735)、
[OSV](https://github.com/cosmos-arc/ditto/actions/runs/34007684137/job/101417834802)、
[Trivy](https://github.com/cosmos-arc/ditto/actions/runs/34007684137/job/101417834881)。
这些是扫描时点的发现，不能当作新提交已扫描通过。

## CodeQL 与远程保护

日志显示 Python 查询完成并解释为 SARIF，上传返回 “Advanced Security must be enabled”。
只读仓库 API 返回 private=true、security_and_analysis=null；main protection API 返回 HTTP 403，
要求升级 GitHub Pro 或改为公开仓库。因此 required checks **未核验**，不能宣称保护已生效。

分析与上传已经拆成单独步骤，SARIF 先保存为普通 CI artifact。使用已固定版本的
[CodeQL analyze inputs](https://github.com/github/codeql-action/blob/cdf488f595d80d6e07e03d4674febd5ab45fa938/analyze/action.yml)
中的 `upload: never` 与 `upload-database: false`，随后独立执行 upload-sarif。
上传不可用仍使安全 gate 失败；没有改远程权限、付费配置或设置成功兜底。
管理员需另行决定服务授权，并核实稳定 `CI gate` 的 required-check 绑定。

## 漏洞清单与适用性

[逐项台账](security-findings.csv) 保留扫描器、ID、组件、安装/修复版本、扫描 subject、
适用性证据和后续动作。OSV 命中的是受版本控制的 sandbox SBOM，并非仅应用 lockfile；
其 image-manifest 绑定 sandbox 镜像与 SBOM hash，不能因文件是 JSON 就从扫描中排除。

Trivy 命中后端镜像中的 Debian 包、Python 发行包和嵌入的 Rust crate。
包括 Mako、PyJWT、cryptography、python-multipart、starlette 与 urllib3。
这些组件存在于扫描 subject；具体调用路径是否可利用尚未逐项证明，台账明确保留这一限制。
没有依据把 `will_not_fix`、非 root 运行或当前未找到直接 import 当成误报。
Debian backport、zlib/minizip 的二进制适用范围需用供应商证据逐项复核后才能豁免。

本轮不升级生产依赖、不更换基础镜像、不新增 ignore。下一步按台账拆分依赖/镜像更新，
保持原有 coverage、PIT、sandbox 隔离和 release cohort 证明；真实漏洞仍阻断完整安全/发布结论。
后端镜像的 SBOM、Trivy JSON 与 smoke 已统一到现有 artifact gate 的一次构建输出，
安全工作流不再另建一份没有完整 cohort 身份的镜像。
