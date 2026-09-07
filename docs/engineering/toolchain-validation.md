# uv / Task / Bun 迁移验收记录

实施范围：[#101](https://github.com/cosmos-arc/ditto/issues/101) 与 #102–#108。基线为 `2e8b8818634275a4eba60b460d01434966ab5b15`，实施分支为 `codex/uv-bun-toolchain`。本记录日期为 2026-09-06。

Python 已改为 uv workspace 与单一 uv.lock；根任务改为 Task；Bun 版本、isolated 安装和脚本信任策略保留。固定 Node 执行 Node CLI。版本、准备命令、原包映射及性能基线见 [工具链说明](toolchain.md)。历史发布、验收和研究记录未覆盖。

## 已执行的本机验证

环境：macOS ARM64，CPython 3.13.14，uv 0.12.7，Task 3.53.1，Node 24.20.0，Bun 1.3.14；新 worktree 的 `.venv`，未使用旧 Pixi 环境补包。

| 验证 | 实际结果 |
| --- | --- |
| 全量后端 pytest 与覆盖率 | 16,470 passed、73 skipped；覆盖率 89.41%，既有阈值通过 |
| PIT | 401 passed、16,146 deselected |
| Python source + tests 类型 | 0 errors |
| Ruff、格式、pre-commit | 通过 |
| Python import 边界与 architecture smells | 通过 |
| Web 类型、构建、架构、Biome | 通过 |
| Web 覆盖率测试 | 208 文件、1,757 tests 通过 |
| Web 原型测试 | 719 tests 通过 |
| 契约 snapshot、oasdiff、生成零差异、conformance | 通过 |
| production Web + 真实 API 系统验收 | 主流程与 outage、timeout、mismatch、restart、approval、governance 场景通过 |
| Harness | 政策、lease、工具测试、类型与大小门通过；Bun 缺包/越界反例已接入常规入口 |
| release/security 单元测试 | 108 passed，含离线 bundle 自包含执行与环境错配拒绝 |
| 独立 production 环境 | no-dev、non-editable；在 `/tmp` 使用 `python -I` 导入后端并生成 API app 成功 |
| Docker Linux x86_64 构建 | 通过；本机模拟运行因 Polars AVX 指令集不匹配失败，不计作 Linux runtime 通过 |

73 个跳过沿用既有真实数据/凭据/隔离条件，本次未增加跳过。全量本机覆盖率未提供 base ref，因此未执行 changed-code 阈值。全量后端测试之后，PIT 入口曾等待个人 Keychain；改为与普通测试相同的空 Keyring 后，单独重跑 PIT 与架构门通过，未把被中断的复合命令记作完整成功。

## 原生 CI 与未完成项

[第一轮 CI](https://github.com/cosmos-arc/ditto/actions/runs/34037542007) 和 [第二轮 CI](https://github.com/cosmos-arc/ditto/actions/runs/34038391277) 提供真实平台证据。第二轮已经通过工具链安装、后端类型/格式、架构/Harness、契约、release policy 及 Linux 真实双栈系统验收、Web CI。macOS 原生平台门全部通过；Windows 原生库行为与双栈类型检查通过。

以下阻断仍不能宣称完成：

1. **Windows 后端启动**：原基线的 `ditto_analysis/research/_artifact_file_primitives.py` 与 `_indexed_artifacts.py` 在导入时使用 POSIX 专用 `os.O_NOFOLLOW` / `os.O_DIRECTORY`。Windows 普通 API/CLI 导入因此失败。需要保持防符号链接与目录句柄安全语义的 Windows 实现，不能把安全标志设为零或跳过平台门。
2. **OSV**：第一轮扫描报告 30 个包、161 条漏洞。报告列出的 uv.lock Python 包版本均已在原锁存在；Bun 的包版本未改动，沙箱 SBOM 也未改动。本次不扩展成无关依赖升级，不豁免漏洞门。
3. **CodeQL 上传**：本地分析可运行，但 GitHub 拒绝上传，明确要求为该仓库启用 Advanced Security；未修改权限或把服务拒绝改为成功。
4. **Linux 生产制品及最终整仓绿灯**：[原生镜像任务](https://github.com/cosmos-arc/ditto/actions/runs/34038391277/job/101502704807) 已完成构建、SBOM subject 校验、非 root readiness 与 release identity 检查；随后 Trivy 扫描退出 1，因此未进入 cohort 打包成功路径。镜像 subject 为 `sha256:0923aa86bcafe6e1e34b0ffebe4f7095a2ff6cbb8e83e2bc0dc6a9c95da229c6`。[保留的扫描证据](https://github.com/cosmos-arc/ditto/actions/runs/34038391277/artifacts/9991178122) 可供追查。最新 PR CI 仍应核对，不能把这个原生运行证明扩大为完整发布通过。

旧 Gitleaks 8.18.4 将 `parso==0.8.7` sdist 的公开 SHA-256 误识别为 Square token。已对照 [PyPI 发布元数据](https://pypi.org/pypi/parso/0.8.7/json)，仅按仓库既有模式登记准确的历史/当前树 finding 指纹；迁移提交范围复扫无泄漏，未放宽路径或规则。

## 双轴审查

- **Standards**：修复 uv add/remove `--no-sync` 和子进程参数绕过 lease、CI Playwright 路径错误；复审未发现新的可复现阻断。Linux leader 回收与 SQLite 显式关闭均保留安全语义。
- **Spec**：修复只读入口偷偷创建环境、Bun 传递依赖/跨 worktree 回退、离线镜像环境事实不绑定输入，以及历史记录被误改；离线 verifier/bundle 33 项定向测试通过，历史 review/plan/验收记录已恢复。

当前分支可供审查，但由于上述原生 Windows、漏洞与服务阻断，#101 及最终平台/发布/清理验收票不能标记为全部完成。

## 2026-09-07 追加收口

- Windows 导入阻断已修复：artifact open 辅助层不再在 import 时读取 POSIX 专用标志；Windows 已存在条目改用 Win32/NT 的 no-reparse-point 原生打开并锚定父目录句柄，mkdir/stat/unlink/硬链接发布也使用同一安全入口。目录读取默认请求只读访问，只有需要 Windows 目录 flush 的 publication path 使用 `GENERIC_WRITE` durable 句柄；staged 文件以 `O_RDWR` 打开以满足 flush 契约，artifact service 的父目录同步同样经该入口。其他缺少原子 `O_NOFOLLOW` 的平台 fail closed，非 Windows `O_CREAT | O_EXCL` 保持 0600 模式。新增回归覆盖 POSIX 标志缺失 import、最终 symlink 拒绝、目录 fail closed、创建模式、Windows native 路径分发及文件/目录 flush。
- Linux 后端测试不再硬编码 macOS `/private/tmp`；CMP live fixture 使用平台临时目录，消除 CI 上的 `FileNotFoundError`。
- `uv.lock` 仅针对 OSV 报告的受影响 Python 包收敛/升级（包括 Prefect 3.6.29、cryptography 50.0.1、Starlette 1.6.0、urllib3 2.7.0 等）。本地固定 OSV scanner 复扫：`uv.lock` 390 包、`bun.lock` 673 包均无命中；resolver 同时消除了此前跨平台的重复版本分支。
- 追加本机验证：后端全量 pytest 与覆盖率门通过（16,474 passed / 73 skipped，覆盖率 89.41%）；Python source/tests 类型、PIT 401 passed、架构/Harness、契约、真实双栈系统验收、Web 1,757 覆盖率测试与 719 原型测试通过。第一次复合 `task ci` 只因本机 shell 使用 Node 24.18.0 / 未暴露 Task binary 中断；用仓库固定 Node 24.20.0 与 Task 3.53.1 后逐项补跑通过。
- 仍不能宣称最终安全/发布完成：受版本控制的 agent sandbox SBOM 复扫仍有 102 包、109 条命中；CodeQL 上传仍要求仓库启用 Advanced Security；Trivy 后端镜像与最终 CI 需在新提交上真实复扫。没有新增 ignore、豁免或降低严重级门槛。
- 新提交 `b39637e5` 推送后，GitHub 在 Repository policy 和 CI gate 启动前拒绝运行：[run 34082462799](https://github.com/cosmos-arc/ditto/actions/runs/34082462799) 的 annotation 为 “recent account payments have failed or your spending limit needs to be increased”。这不是代码门结果；Windows、Trivy 与最终 cohort 仍等待 billing/spending limit 恢复后由新提交复跑。
- 复审后续修复：不支持的缺少原子 `O_NOFOLLOW` 平台直接 fail closed，POSIX-only import 检查移入固定解释器子进程避免 reload 污染，indexed artifact 复用同一 read flags；R3 fixture 验收改为固定 Node 运行 Vitest，CI setup 统一拥有 locked Bun/Python 安装并移除重复 raw install，补齐同机迁移前后 Bun 冷/热安装与 `web-type` 对比。本机复验：Ruff lint/format 通过，Python source/tests 类型 0 errors，artifact primitives/service 78 passed/1 Windows-only skipped，platform backend unit 108 passed/1 Windows-only skipped，R3 acceptance contract 15 passed，fixture suite 29 passed；当前未提交状态的 composite `task check` 通过，其中 fast 后端 15,452 passed/1 skipped、Web 覆盖率测试 1,757 passed，契约、架构、Harness 与 tooling 门均通过；Windows 平台单元已加入 artifact primitives/service 用例，真实 runner 证据仍受 billing 阻断。
