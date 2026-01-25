"""
配置 Provider（Composition Root）.

所有配置通过 DI 容器注入，在应用层（port）统一管理配置加载。
Foundation 层只提供基础设施（Environment、ConfigLoader、Settings 类）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_core.quality.config import DQSettings
from ditto_datahub.config import (
    DatabaseSettings,
    DataSourceSettings,
    FileStorageSettings,
)
from ditto_foundation.config import (
    ConfigLoader,
    Environment,
)
from ditto_foundation.config.paths import get_paths
from ditto_foundation.config.settings import (
    Settings,
)
from ditto_foundation.observability import init, shutdown
from ditto_foundation.observability.config import ObservabilityConfig
from dotenv import dotenv_values

__all__ = ["ConfigProvider"]


class ConfigProvider(Provider):
    """
    统一配置提供者（Composition Root）.

    职责：
        1. 根据环境创建 ConfigLoader
        2. 从 config/{env}/*.env 加载所有配置
        3. 提供统一的配置访问接口
        4. 注入环境信息到各个配置

    架构分层：
        Foundation: Settings 类定义（不依赖 DI）
        DataHub: 数据相关配置
        Port (这里): ConfigProvider 组装所有配置
    """

    scope = Scope.APP  # 应用级单例

    @provide
    def environment(self) -> Environment:
        """
        运行时环境（应用级单例）.

        从 DITTO_ENV 环境变量读取，默认为 development.
        """
        env_str = os.getenv("DITTO_ENV", "development")
        return Environment.from_str(env_str)

    @provide
    def config_loader(self, environment: Environment) -> ConfigLoader:
        """配置加载器（应用级单例）."""
        return ConfigLoader(environment)

    @provide
    def data_root(self) -> Path:
        """数据根目录."""
        return get_paths().data_home

    @provide
    def settings(
        self,
        config_loader: ConfigLoader,
    ) -> Settings:
        """
        主配置 Settings（应用级单例）.

        从 env 文件加载配置，保持配置加载逻辑统一。
        注：database/data_source 已迁移到 DataHub 层，由独立 provider 加载。
        """
        # 只加载 Settings 类实际包含的配置
        observability_values = dotenv_values(
            config_loader.get_env_file("observability")
        )
        system_values = dotenv_values(config_loader.get_env_file("system"))

        # 使用 model_validate 创建配置实例
        return Settings.model_validate(
            {
                "observability": observability_values,
                "system": system_values,
            }
        )

    @provide
    def dq_settings(
        self,
        config_loader: ConfigLoader,
        environment: Environment,
    ) -> DQSettings:
        """
        DQ 配置（应用级单例）.

        ✅ 统一规则：从 config/{env}/dq.env 加载
        ✅ 注入环境信息，DQSettings 无需内部读取 get_settings()
        """
        dq_values = dotenv_values(config_loader.get_env_file("dq"))
        # 注入环境信息
        return DQSettings.model_validate(
            {
                **dq_values,
                "env": environment.value,  # 注入环境
            }
        )

    @provide
    def database_settings(
        self,
        config_loader: ConfigLoader,
    ) -> DatabaseSettings:
        """
        Database 配置（应用级单例）.

        ✅ 统一规则：从 config/{env}/database.env 加载
        ✅ DataHub 层配置：通过 DI 容器注入，与 Foundation 解耦
        """
        database_values = dotenv_values(config_loader.get_env_file("database"))
        return DatabaseSettings.model_validate(database_values)

    @provide
    def data_source_settings(
        self,
        config_loader: ConfigLoader,
    ) -> DataSourceSettings:
        """
        DataSource 配置（应用级单例）.

        ✅ 统一规则：从 config/{env}/data_source.env 加载
        ✅ DataHub 层配置：通过 DI 容器注入，与 Foundation 解耦
        """
        data_source_values = dotenv_values(config_loader.get_env_file("data_source"))
        return DataSourceSettings.model_validate(data_source_values)

    @provide
    def file_storage_settings(
        self,
        config_loader: ConfigLoader,
    ) -> FileStorageSettings:
        """
        FileStorage 配置（应用级单例）.

        ✅ 统一规则：从 config/{env}/system.env 加载（共用 system.env）
        ✅ DataHub 层配置：通过 DI 容器注入，与 Foundation 解耦
        """
        system_values = dotenv_values(config_loader.get_env_file("system"))
        return FileStorageSettings.model_validate(system_values)

    @provide
    def observability(
        self,
        settings: Settings,
    ) -> Iterator[None]:
        """
        Observability 初始化（应用级单例）.

        生命周期：容器启动时初始化，容器关闭时调用 shutdown().
        """
        config = settings.observability
        ditto_env = settings.system.ditto_env

        # 动态检测运行时标志（pytest、assertions、verbose）
        runtime_flags = ObservabilityConfig.detect_runtime_flags(ditto_env)

        init(
            service_name="ditto-server",
            environment=ditto_env.value,
            log_level=config.log_level,
            log_dir="logs",
            vm_endpoint=config.vm_endpoint,
            pytest_running=runtime_flags["pytest_running"],
            assertions_enabled=runtime_flags["assertions_enabled"],
            verbose_logging=runtime_flags["verbose_logging"],
        )

        yield

        # 容器关闭时调用 shutdown
        shutdown()
