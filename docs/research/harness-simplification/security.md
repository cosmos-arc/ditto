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

## 本地复验补充

linked worktree 的 `.git` 指向主仓库 common-dir，原容器只挂载工作目录，导致两版 gitleaks
历史扫描出现 Git 错误却返回成功。现在只读挂载实际 common-dir，并先在容器内验证 Git HEAD；
真实复验分别扫描 734 / 738 个提交（扫描期间有本地提交），不再将无法读取历史当作成功。
临时真实 Git worktree 的回归先失败、修复后通过，安全/仓库政策 36 项测试通过。

旧版当前树扫描还识别到 `test_repository_policy.py` 的已知合成 PAT 哨兵。
测试改为运行时构造同一字符串，断言和 workflow 的检测哨兵保持不变，没有新增 ignore。
最终两版历史/当前树扫描无告警，两版注入哨兵均按预期拒绝。

本地 OSV 摘要为 11 个包、85 条已知漏洞（5 Critical、36 High、36 Medium、4 Low、4 Unknown），
仍非零退出；明细中的 86 个 advisory 标识与上述历史台账一致，不能据摘要计数差异宣称漏洞已修复。
具体风险及依赖更新仍按逐项台账处理。

提交 `517eeb12` 的实际 x86 Linux 镜像复验新增 [当前 Trivy 台账](trivy-current.csv)：
69 条组件发现（65 HIGH、4 CRITICAL，31 个不同 advisory），无秘密发现；没有发布放行。
原 artifact gate 因默认数据库镜像 EOF 非零退出，改用扫描器自带另一官方源后，对同一 tar 完成扫描，
并核对 Trivy ImageID 与 Syft/导出 config digest 一致；构建及 digest 详见 [实施报告](implementation.md)。
扫描器明确提示 Conda 包只支持 SBOM、尚不支持漏洞扫描，后续依赖审视须保留这一覆盖缺口。
