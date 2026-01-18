"""
配置初始化命令.

提供配置初始化的 CLI 命令，支持初始化所有配置、DQ 配置或数据库 Schema。
"""

from pathlib import Path

import typer
from ditto_datahub import register_datahub_providers
from ditto_foundation.config.initializer import InitScope, get_config_coordinator
from ditto_foundation.config.paths import get_paths

app = typer.Typer(help="配置初始化命令")


@app.command()
def config(
    ctx: typer.Context,
    data_root: str | None = typer.Option(None, "--data-root", "-d", help="数据根目录"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新初始化"),
) -> None:
    """
    初始化所有配置.

    初始化包括 DQ 配置和数据库 Schema。

    Examples:
        初始化所有配置（使用默认数据根目录）:
        $ ditto init config

        初始化所有配置（指定数据根目录）:
        $ ditto init config --data-root /path/to/data

        强制重新初始化:
        $ ditto init config --force

    """
    # 确定数据根目录
    if data_root is None:
        data_root = ctx.obj.get("data_root")
    data_root_path: Path = (
        get_paths().data_home if data_root is None else Path(data_root)
    )

    # 注册配置提供者
    register_datahub_providers()

    # 执行初始化
    coordinator = get_config_coordinator()
    scope = InitScope.ALWAYS if force else InitScope.MANUAL
    results = coordinator.initialize(scope=scope, data_root=data_root_path, force=force)

    # 输出结果
    all_success = True
    for provider, result in results.items():
        if result.success:
            if result.skipped:
                typer.echo(f"⊙ {provider}: {result.message}")
            else:
                typer.echo(f"✓ {provider}: {result.message}")
        else:
            typer.echo(f"✗ {provider}: {result.message}", err=True)
            all_success = False

    if not all_success:
        raise typer.Exit(1)


@app.command()
def dq(
    ctx: typer.Context,
    data_root: str | None = typer.Option(None, "--data-root", "-d", help="数据根目录"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新初始化"),
) -> None:
    """
    仅初始化 DQ 配置.

    Examples:
        初始化 DQ 配置:
        $ ditto init dq

        强制重新初始化:
        $ ditto init dq --force

    """
    # 确定数据根目录
    if data_root is None:
        data_root = ctx.obj.get("data_root")
    data_root_path: Path = (
        get_paths().data_home if data_root is None else Path(data_root)
    )

    # 注册配置提供者
    register_datahub_providers()

    # 执行初始化
    coordinator = get_config_coordinator()
    scope = InitScope.ALWAYS if force else InitScope.MANUAL

    # 只初始化 dq_config 提供者
    results = coordinator.initialize(scope=scope, data_root=data_root_path, force=force)

    # 过滤只显示 dq_config 结果
    dq_results = {
        provider: result
        for provider, result in results.items()
        if "dq" in provider.lower()
    }

    # 输出结果
    all_success = True
    for provider, result in dq_results.items():
        if result.success:
            if result.skipped:
                typer.echo(f"⊙ {provider}: {result.message}")
            else:
                typer.echo(f"✓ {provider}: {result.message}")
        else:
            typer.echo(f"✗ {provider}: {result.message}", err=True)
            all_success = False

    if not all_success:
        raise typer.Exit(1)


@app.command()
def db(
    ctx: typer.Context,
    data_root: str | None = typer.Option(None, "--data-root", "-d", help="数据根目录"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新初始化"),
) -> None:
    """
    仅初始化数据库 Schema.

    Examples:
        初始化数据库:
        $ ditto init db

        强制重新初始化:
        $ ditto init db --force

    """
    # 确定数据根目录
    if data_root is None:
        data_root = ctx.obj.get("data_root")
    data_root_path: Path = (
        get_paths().data_home if data_root is None else Path(data_root)
    )

    # 注册配置提供者
    register_datahub_providers()

    # 执行初始化
    coordinator = get_config_coordinator()
    scope = InitScope.ALWAYS if force else InitScope.MANUAL

    # 只初始化 database_schema 提供者
    results = coordinator.initialize(scope=scope, data_root=data_root_path, force=force)

    # 过滤只显示 database_schema 结果
    db_results = {
        provider: result
        for provider, result in results.items()
        if "database" in provider.lower() or "schema" in provider.lower()
    }

    # 输出结果
    all_success = True
    for provider, result in db_results.items():
        if result.success:
            if result.skipped:
                typer.echo(f"⊙ {provider}: {result.message}")
            else:
                typer.echo(f"✓ {provider}: {result.message}")
        else:
            typer.echo(f"✗ {provider}: {result.message}", err=True)
            all_success = False

    if not all_success:
        raise typer.Exit(1)
