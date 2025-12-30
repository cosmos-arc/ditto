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
    - 只记录文件 SHA-256 checksum（v2.0+），向后支持 MD5（v1.0）
    - 文件路径相对于 data_root
    - Manifest 存储在 {data_root}/freezes/
    """

    def __init__(self, data_root: str, default_ttl_days: int = 90) -> None:
        """
        初始化 FreezeManager。

        Args:
            data_root: 数据根目录
            default_ttl_days: 默认 TTL 天数（清理时使用）

        """
        self._data_root = Path(data_root)
        self._freezes_dir = self._data_root / "freezes"
        self._freezes_dir.mkdir(parents=True, exist_ok=True)
        self._default_ttl_days = default_ttl_days

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
            ValueError: freeze_id 包含非法字符

        """
        logger.info(
            "freeze_create_start",
            event="freeze_create",
            freeze_id=freeze_id,
            datasets_count=len(datasets),
        )

        # Validate freeze_id for path traversal protection
        self._validate_freeze_id(freeze_id)

        # Collect checksums for all datasets
        files = self._collect_checksums(freeze_id, datasets)

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
        errors = self._verify_files(manifest)

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

    def cleanup_expired(self, max_age_days: int | None = None) -> list[str]:
        """
        清理过期的 freeze manifest。

        Args:
            max_age_days: 最大保留天数，None 使用默认值

        Returns:
            删除的 freeze_id 列表

        """
        max_age = max_age_days or self._default_ttl_days
        logger.info(
            "cleanup_expired_start",
            event="cleanup_expired",
            max_age_days=max_age,
        )

        from datetime import datetime, timedelta

        cutoff = datetime.now() - timedelta(days=max_age)
        deleted = []

        for manifest_path in self._freezes_dir.glob("*.json"):
            try:
                manifest = self._load_manifest(manifest_path)
                created = datetime.fromisoformat(manifest.created_at)

                if created < cutoff:
                    freeze_id = manifest.freeze_id
                    self.delete(freeze_id)
                    deleted.append(freeze_id)
            except Exception as e:
                logger.warning(
                    "cleanup_manifest_failed",
                    event="cleanup_expired",
                    manifest_path=manifest_path.name,
                    error=str(e),
                )

        logger.info(
            "cleanup_expired_complete",
            event="cleanup_expired",
            deleted_count=len(deleted),
        )

        return deleted

    def _validate_freeze_id(self, freeze_id: str) -> None:
        """
        验证 freeze_id 不包含路径遍历字符。

        Args:
            freeze_id: Freeze ID

        Raises:
            ValueError: freeze_id 包含非法字符

        """
        if "/" in freeze_id or "\\" in freeze_id or ".." in freeze_id:
            raise ValueError(
                "Invalid freeze_id: cannot contain path separators or '..'"
            )

    def _collect_checksums(
        self,
        freeze_id: str,
        datasets: list[str],
    ) -> dict[str, str]:
        """
        收集所有数据集的 checksum。

        支持两种模式：
        1. 单文件：{dataset}.parquet
        2. 分区目录：{dataset}/**/*.parquet（匹配所有分区文件）

        Args:
            freeze_id: Freeze ID（用于日志）
            datasets: 数据集列表

        Returns:
            {相对路径: checksum} 字典

        Raises:
            FileNotFoundError: 任何数据集文件不存在

        """
        files: dict[str, str] = {}
        missing_files: list[str] = []

        for dataset in datasets:
            # Try single file first (e.g., "stock_daily.parquet")
            single_file_path = self._data_root / f"{dataset}.parquet"

            if single_file_path.exists():
                # Single file mode
                checksum = self._compute_checksum(single_file_path)
                rel_path = single_file_path.relative_to(self._data_root).as_posix()
                files[rel_path] = checksum
                continue

            # Try partitioned directory (e.g., "stock_daily/**/*.parquet")
            dataset_dir = self._data_root / dataset
            if dataset_dir.exists() and dataset_dir.is_dir():
                # Find all .parquet files in the dataset directory
                parquet_files = list(dataset_dir.rglob("*.parquet"))
                if parquet_files:
                    for parquet_file in parquet_files:
                        checksum = self._compute_checksum(parquet_file)
                        rel_path = parquet_file.relative_to(self._data_root).as_posix()
                        files[rel_path] = checksum
                    continue

            # Neither single file nor directory found
            if single_file_path.parent.exists():
                rel_path = single_file_path.relative_to(self._data_root).as_posix()
            else:
                rel_path = f"{dataset}.parquet"
            missing_files.append(rel_path)

        # 如果有文件缺失，抛出异常
        if missing_files:
            raise FileNotFoundError(
                f"Datasets not found for freeze '{freeze_id}': {missing_files}"
            )

        return files

    def _verify_files(self, manifest: FreezeManifest) -> list[str]:
        """
        验证 manifest 中所有文件的 checksum。

        Args:
            manifest: Freeze manifest

        Returns:
            错误列表（空列表表示全部通过）

        """
        errors: list[str] = []

        for rel_path, expected_checksum in manifest.files.items():
            file_path = self._data_root / rel_path

            # 检查文件是否存在
            if not file_path.exists():
                errors.append(f"File missing: {rel_path}")
                continue

            # 根据校验和类型使用不同的验证方法
            if manifest.checksum_type == "md5":
                # 对于 MD5，仍然使用 MD5 算法验证
                actual_checksum = self._compute_md5_checksum(file_path)
            else:
                # 对于 SHA-256，使用新的 SHA-256 算法验证
                actual_checksum = self._compute_checksum(file_path)

            if actual_checksum != expected_checksum:
                errors.append(f"Checksum mismatch: {rel_path}")

        return errors

    def _compute_checksum(self, file_path: Path) -> str:
        """
        计算文件的 SHA-256 checksum。

        Args:
            file_path: 文件路径

        Returns:
            SHA-256 hex string

        """
        sha256 = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _compute_md5_checksum(self, file_path: Path) -> str:
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
            "version": manifest.version,
            "checksum_type": manifest.checksum_type,
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

        # 向后兼容：旧格式可能没有 version 和 checksum_type 字段
        version = data.get("version", "1.0")  # 默认为旧版本
        checksum_type = data.get(
            "checksum_type", "md5" if version == "1.0" else "sha256"
        )

        return FreezeManifest(
            freeze_id=data["freeze_id"],
            description=data["description"],
            created_at=data["created_at"],
            version=version,
            checksum_type=checksum_type,
            files=data["files"],
        )
