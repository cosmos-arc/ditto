"""Freeze manager for lightweight data version tracking."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from ditto_foundation import logger, traced

from ..types import FreezeManifest


class FreezeManager:
    """
    轻量级数据版本管理：仅记录 checksum，不复制文件。

    设计原则：
    - Freeze = 轻量级可复现
    - 只记录文件 MD5 checksum
    - 文件路径相对于 data_root
    - Manifest 存储在 {data_root}/freezes/
    """

    def __init__(self, data_root: str) -> None:
        """
        初始化 FreezeManager。

        Args:
            data_root: 数据根目录

        """
        self._data_root = Path(data_root)
        self._freezes_dir = self._data_root / "freezes"
        self._freezes_dir.mkdir(parents=True, exist_ok=True)

    @traced("freeze.create")
    def create(
        self,
        freeze_id: str,
        description: str,
        datasets: list[str],
    ) -> FreezeManifest:
        """
        创建 freeze manifest（记录数据集的 checksum）。

        Args:
            freeze_id: Freeze ID
            description: 描述
            datasets: 数据集列表（相对路径，如 "bars/stock_daily"）

        Returns:
            FreezeManifest 对象

        Raises:
            FileNotFoundError: 数据集文件不存在

        """
        logger.info(
            "freeze_create_start",
            event="freeze_create",
            freeze_id=freeze_id,
            datasets_count=len(datasets),
        )

        files: dict[str, str] = {}

        for dataset in datasets:
            # 数据集路径 -> 文件路径
            # 支持 parquet 文件
            file_path = self._data_root / f"{dataset}.parquet"

            if not file_path.exists():
                logger.warning(
                    "freeze_file_not_found",
                    event="freeze_create",
                    freeze_id=freeze_id,
                    file_path=file_path.relative_to(self._data_root).as_posix(),
                )
                continue

            # 计算 MD5 checksum
            checksum = self._compute_checksum(file_path)
            rel_path = file_path.relative_to(self._data_root).as_posix()
            files[rel_path] = checksum

        created_at = datetime.now().isoformat()
        manifest = FreezeManifest(
            freeze_id=freeze_id,
            description=description,
            created_at=created_at,
            files=files,
        )

        # 持久化 manifest
        manifest_path = self._freezes_dir / f"{freeze_id}.json"
        self._save_manifest(manifest_path, manifest)

        logger.info(
            "freeze_create_complete",
            event="freeze_create",
            freeze_id=freeze_id,
            file_count=manifest.file_count,
        )

        return manifest

    @traced("freeze.verify")
    def verify(
        self,
        freeze_id: str,
        raise_on_error: bool = False,
    ) -> tuple[bool, list[str]]:
        """
        验证 freeze 的 checksum 是否匹配。

        Args:
            freeze_id: Freeze ID
            raise_on_error: 是否在验证失败时抛出异常

        Returns:
            (是否通过, 错误列表)

        Raises:
            RuntimeError: 验证失败且 raise_on_error=True

        """
        logger.info(
            "freeze_verify_start",
            event="freeze_verify",
            freeze_id=freeze_id,
        )

        manifest = self.get_manifest(freeze_id)
        errors: list[str] = []

        for rel_path, expected_checksum in manifest.files.items():
            file_path = self._data_root / rel_path

            # 检查文件是否存在
            if not file_path.exists():
                errors.append(f"File missing: {rel_path}")
                continue

            # 检查 checksum 是否匹配
            actual_checksum = self._compute_checksum(file_path)
            if actual_checksum != expected_checksum:
                errors.append(f"Checksum mismatch: {rel_path}")

        passed = len(errors) == 0

        if not passed and raise_on_error:
            logger.error(
                "freeze_verify_failed",
                event="freeze_verify",
                freeze_id=freeze_id,
                error_count=len(errors),
            )
            raise RuntimeError(
                f"Freeze verification failed for '{freeze_id}': {errors}"
            )

        logger.info(
            "freeze_verify_complete",
            event="freeze_verify",
            freeze_id=freeze_id,
            passed=passed,
            error_count=len(errors),
        )

        return passed, errors

    @traced("freeze.list")
    def list_freezes(self) -> list[FreezeManifest]:
        """
        列出所有 freeze。

        Returns:
            FreezeManifest 列表（按创建时间倒序）

        """
        logger.info(
            "freeze_list_start",
            event="freeze_list",
        )

        manifests = []
        for manifest_path in self._freezes_dir.glob("*.json"):
            manifest = self._load_manifest(manifest_path)
            manifests.append(manifest)

        # 按创建时间倒序
        manifests.sort(key=lambda m: m.created_at, reverse=True)

        logger.info(
            "freeze_list_complete",
            event="freeze_list",
            freeze_count=len(manifests),
        )

        return manifests

    @traced("freeze.get")
    def get_manifest(self, freeze_id: str) -> FreezeManifest:
        """
        获取 freeze manifest。

        Args:
            freeze_id: Freeze ID

        Returns:
            FreezeManifest 对象

        Raises:
            FileNotFoundError: Freeze 不存在

        """
        manifest_path = self._freezes_dir / f"{freeze_id}.json"

        if not manifest_path.exists():
            raise FileNotFoundError(f"Freeze not found: {freeze_id}")

        return self._load_manifest(manifest_path)

    @traced("freeze.delete")
    def delete(self, freeze_id: str) -> None:
        """
        删除 freeze manifest。

        Args:
            freeze_id: Freeze ID

        """
        logger.info(
            "freeze_delete_start",
            event="freeze_delete",
            freeze_id=freeze_id,
        )

        manifest_path = self._freezes_dir / f"{freeze_id}.json"

        if not manifest_path.exists():
            logger.warning(
                "freeze_not_found",
                event="freeze_delete",
                freeze_id=freeze_id,
            )
            return

        manifest_path.unlink()

        logger.info(
            "freeze_delete_complete",
            event="freeze_delete",
            freeze_id=freeze_id,
        )

    def _compute_checksum(self, file_path: Path) -> str:
        """
        计算文件的 MD5 checksum。

        Args:
            file_path: 文件路径

        Returns:
            MD5 hex string

        """
        md5 = hashlib.md5(usedforsecurity=False)
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5.update(chunk)
        return md5.hexdigest()

    def _save_manifest(self, path: Path, manifest: FreezeManifest) -> None:
        """
        保存 manifest 到文件。

        Args:
            path: 文件路径
            manifest: Manifest 对象

        """
        data = {
            "freeze_id": manifest.freeze_id,
            "description": manifest.description,
            "created_at": manifest.created_at,
            "files": manifest.files,
        }

        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_manifest(self, path: Path) -> FreezeManifest:
        """
        从文件加载 manifest。

        Args:
            path: 文件路径

        Returns:
            FreezeManifest 对象

        """
        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        return FreezeManifest(
            freeze_id=data["freeze_id"],
            description=data["description"],
            created_at=data["created_at"],
            files=data["files"],
        )
