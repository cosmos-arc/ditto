"""配置初始化命令。"""

from __future__ import annotations

from pathlib import Path

import typer
from ditto_platform.foundation.config import ConfigInitCoordinator
from ditto_platform.foundation.config.initializer import InitScope
from ditto_platform.foundation.config.providers import DataRootInitProvider

from ditto_apps.registry.infra.config import (
    data_root_init_directories_from_data_store,
    load_data_store_settings,
)
from ditto_apps.registry.init_providers import MetadataDbInitProvider

app = typer.Typer(help="配置初始化命令")


def _load_data_root() -> Path:
    return load_data_store_settings().data_root


def _resolve_data_root(ctx: typer.Context, data_root: str | None) -> Path:
    if data_root is None:
        data_root = ctx.obj.get("data_root") if ctx.obj else None
    return Path(data_root) if data_root else _load_data_root()


def _make_coordinator() -> ConfigInitCoordinator:
    """创建并注册所有初始化提供者的协调器。"""
    coordinator = ConfigInitCoordinator()
    settings = load_data_store_settings()
    coordinator.register(
        DataRootInitProvider(data_root_init_directories_from_data_store(settings))
    )
    coordinator.register(MetadataDbInitProvider())
    return coordinator


def _init_scope(force: bool) -> InitScope:
    """选择 CLI 初始化作用域。"""
    return InitScope.ALWAYS if force else InitScope.STARTUP


@app.command()
def config(
    ctx: typer.Context,
    data_root: str | None = typer.Option(None, "--data-root", "-d", help="数据根目录"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新初始化"),
) -> None:
    """初始化全部配置资源。"""
    data_root_path = _resolve_data_root(ctx, data_root)

    coordinator = _make_coordinator()
    scope = _init_scope(force)
    results = coordinator.initialize(scope=scope, data_root=data_root_path, force=force)

    all_success = True
    for provider, result in results.items():
        if result.success:
            if result.skipped:
                typer.echo(f"[SKIP] {provider}: {result.message}")
            else:
                typer.echo(f"[OK] {provider}: {result.message}")
        else:
            typer.echo(f"[FAIL] {provider}: {result.message}", err=True)
            all_success = False

    if not all_success:
        raise typer.Exit(1)


@app.command()
def dq(
    ctx: typer.Context,
    data_root: str | None = typer.Option(None, "--data-root", "-d", help="数据根目录"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新初始化"),
) -> None:
    """仅初始化 DQ 相关配置资源。"""
    data_root_path = _resolve_data_root(ctx, data_root)

    coordinator = _make_coordinator()
    scope = _init_scope(force)
    results = coordinator.initialize(scope=scope, data_root=data_root_path, force=force)

    dq_results = {
        provider: result
        for provider, result in results.items()
        if "dq" in provider.lower()
    }

    all_success = True
    for provider, result in dq_results.items():
        if result.success:
            if result.skipped:
                typer.echo(f"[SKIP] {provider}: {result.message}")
            else:
                typer.echo(f"[OK] {provider}: {result.message}")
        else:
            typer.echo(f"[FAIL] {provider}: {result.message}", err=True)
            all_success = False

    if not all_success:
        raise typer.Exit(1)


@app.command()
def db(
    ctx: typer.Context,
    data_root: str | None = typer.Option(None, "--data-root", "-d", help="数据根目录"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新初始化"),
) -> None:
    """仅初始化数据库相关配置资源。"""
    data_root_path = _resolve_data_root(ctx, data_root)

    coordinator = _make_coordinator()
    scope = _init_scope(force)
    results = coordinator.initialize(scope=scope, data_root=data_root_path, force=force)

    db_results = {
        provider: result
        for provider, result in results.items()
        if "database" in provider.lower() or "schema" in provider.lower()
    }

    all_success = True
    for provider, result in db_results.items():
        if result.success:
            if result.skipped:
                typer.echo(f"[SKIP] {provider}: {result.message}")
            else:
                typer.echo(f"[OK] {provider}: {result.message}")
        else:
            typer.echo(f"[FAIL] {provider}: {result.message}", err=True)
            all_success = False

    if not all_success:
        raise typer.Exit(1)
