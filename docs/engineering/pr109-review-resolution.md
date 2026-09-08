# PR #109 评审处理记录

核查基线：`235f14f7`。本轮处理四条未解决评审，保留 Task/uv/Bun 所有权、第三方 wheel 策略及发布安全门。

| 评审 | 判断与处理 | 验证依据 |
| --- | --- | --- |
| [初始化文档仍安装 Pixi](https://github.com/cosmos-arc/ditto/pull/109#discussion_r3951879372) | 成立。更新运维手册，先安装仓库声明的 uv、Task、Bun、Node，再用 `task bootstrap` 创建两栈环境；Python 由 uv 管理。 | 核对根 Taskfile、工具链文档、平台和版本声明；移除本手册的 Pixi 安装命令。 |
| [no-build 阻止 workspace 构建](https://github.com/cosmos-arc/ditto/pull/109#discussion_r3953938614) | 不成立。uv 0.12.7 仍允许 first-party workspace 和 editable 构建，保留禁止第三方 sdist 的策略，并补充配置注释。 | 固定 uv 0.12.7 在两个全新环境、`--no-cache` 下分别成功构建并安装 ditto-kernel 的 editable 与非 editable 形式；原全量 CI 也成功安装 workspace 和构建生产镜像。 |
| [Windows 硬链接需 DELETE 权限](https://github.com/cosmos-arc/ditto/pull/109#discussion_r3954150963) | 该权限要求不成立，但原注释误标 DELETE 属实。修正注释，保持现有访问掩码；增加真实文件系统硬链接创建、同文件身份和拒绝覆盖验收，交由原 Windows 门执行。 | Microsoft FILE_LINK_INFORMATION 文档未要求额外访问权；删除/重命名与创建硬链接的权限要求不同。已有 Windows 全量 CI 成功，新用例不 mock Win32/NT 调用。 |
| [发布二次扫描校验丢失 ImageID](https://github.com/cosmos-arc/ditto/pull/109#discussion_r3954150966) | 成立。去掉 SBOM 阶段缺少独立 ImageID 的重复调用。前面的 `scan-backend-sources` 仍校验 pinned digest、选择 amd64 archive、绑定报告 ImageID，并核查最终镜像的易受攻击复制文件。 | 新增 digest-only 报告匹配/不匹配回归；workflow 约束禁止再次调用不带 image_id 的校验。原始报告和来源 SPDX 继续纳入发布 cohort、校验和与长期证据。 |

## 主要来源

- [uv CLI 的 no-build 语义](https://docs.astral.sh/uv/reference/cli/#uv-sync--no-build)。以仓库固定版本的实际构建结果补充在线文档。
- [Microsoft FILE_LINK_INFORMATION](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_link_information)。
- [Microsoft NtSetInformationFile](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ntsetinformationfile)。

本机定向验收：150 passed、1 个 Windows 原生条件跳过；原生 Windows 验收以该提交的 CI 为准。没有触发正式发布。
