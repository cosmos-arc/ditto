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

[第一轮 CI](https://github.com/cosmos-arc/ditto/actions/runs/34037542007) 和 [第二轮 CI](https://github.com/cosmos-arc/ditto/actions/runs/34038391277) 提供真实平台证据。第二轮已经通过工具链安装、后端类型/格式、架构/Harness、契约、release policy 及 Linux 真实双栈系统验收。macOS 原生平台门全部通过；Windows 原生库行为与双栈类型检查通过。

以下阻断仍不能宣称完成：

1. **Windows 后端启动**：原基线的 `ditto_analysis/research/_artifact_file_primitives.py` 与 `_indexed_artifacts.py` 在导入时使用 POSIX 专用 `os.O_NOFOLLOW` / `os.O_DIRECTORY`。Windows 普通 API/CLI 导入因此失败。需要保持防符号链接与目录句柄安全语义的 Windows 实现，不能把安全标志设为零或跳过平台门。
2. **OSV**：第一轮扫描报告 30 个包、161 条漏洞。报告列出的 uv.lock Python 包版本均已在原锁存在；Bun 的包版本未改动，沙箱 SBOM 也未改动。本次不扩展成无关依赖升级，不豁免漏洞门。
3. **CodeQL 上传**：本地分析可运行，但 GitHub 拒绝上传，明确要求为该仓库启用 Advanced Security；未修改权限或把服务拒绝改为成功。
4. **Linux 生产制品及最终整仓绿灯**：以分支最新 CI 为准；本机 x86 模拟运行、解析成功和单元 fixture 不能替代原生生产镜像 readiness、扫描及 cohort 验收。

旧 Gitleaks 8.18.4 将 `parso==0.8.7` sdist 的公开 SHA-256 误识别为 Square token。已对照 [PyPI 发布元数据](https://pypi.org/pypi/parso/0.8.7/json)，仅按仓库既有模式登记准确的历史/当前树 finding 指纹；迁移提交范围复扫无泄漏，未放宽路径或规则。

## 双轴审查

- **Standards**：修复 uv add/remove `--no-sync` 和子进程参数绕过 lease、CI Playwright 路径错误；复审未发现新的可复现阻断。Linux leader 回收与 SQLite 显式关闭均保留安全语义。
- **Spec**：修复只读入口偷偷创建环境、Bun 传递依赖/跨 worktree 回退、离线镜像环境事实不绑定输入，以及历史记录被误改；离线 verifier/bundle 33 项定向测试通过，历史 review/plan/验收记录已恢复。

当前分支可供审查，但由于上述原生 Windows、漏洞与服务阻断，#101 及最终平台/发布/清理验收票不能标记为全部完成。
