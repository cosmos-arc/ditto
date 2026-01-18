"""Freeze manager for lightweight data version tracking."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import orjson
from ditto_foundation import logger, traced
from ditto_foundation.version import compute_checksum

from ..models import FreezeManifest


class FreezeManager:
    """
    轻量级数据版本管理：仅记录 checksum，不复制文件。

    设计原则：
    - Freeze = 轻量级可复现
    - 使用 SHA-256 checksum 记录文件指纹
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

        manifests: list[FreezeManifest] = []
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

        cutoff = datetime.now() - timedelta(days=max_age)
        deleted: list[str] = []

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

    def _try_single_file_mode(self, dataset: str) -> dict[str, str] | None:
        """
        尝试单文件模式（{dataset}.parquet）。

        Args:
            dataset: 数据集名称

        Returns:
            checksums 字典或 None（文件不存在时）

        """
        single_file_path = self._data_root / f"{dataset}.parquet"

        if single_file_path.exists():
            checksum = compute_checksum(single_file_path)
            rel_path = single_file_path.relative_to(self._data_root).as_posix()
            return {rel_path: checksum}

        return None

    def _try_partitioned_directory_mode(self, dataset: str) -> dict[str, str] | None:
        """
        尝试分区目录模式（{dataset}/**/*.parquet）。

        Args:
            dataset: 数据集名称

        Returns:
            checksums 字典或 None（目录不存在或为空时）

        """
        dataset_dir = self._data_root / dataset

        if dataset_dir.exists() and dataset_dir.is_dir():
            parquet_files = list(dataset_dir.rglob("*.parquet"))
            if parquet_files:
                files: dict[str, str] = {}
                for parquet_file in parquet_files:
                    checksum = compute_checksum(parquet_file)
                    rel_path = parquet_file.relative_to(self._data_root).as_posix()
                    files[rel_path] = checksum
                return files

        return None

    def _handle_missing_files(self, freeze_id: str, missing_files: list[str]) -> None:
        """
        处理缺失文件（抛出异常）。

        Args:
            freeze_id: Freeze ID
            missing_files: 缺失文件列表

        Raises:
            FileNotFoundError: 当有文件缺失时

        """
        if missing_files:
            raise FileNotFoundError(
                f"Datasets not found for freeze '{freeze_id}': {missing_files}"
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
            # Try single file first
            if checksums := self._try_single_file_mode(dataset):
                files.update(checksums)
                continue

            # Try partitioned directory
            if checksums := self._try_partitioned_directory_mode(dataset):
                files.update(checksums)
                continue

            # Track missing
            missing_files.append(f"{dataset}.parquet")

        # Handle missing files
        self._handle_missing_files(freeze_id, missing_files)

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

            # 使用 SHA-256 验证
            actual_checksum = compute_checksum(file_path)

            if actual_checksum != expected_checksum:
                errors.append(f"Checksum mismatch: {rel_path}")

        return errors

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

        # 使用 orjson 序列化，返回 bytes
        json_bytes = orjson.dumps(
            data,
            option=orjson.OPT_INDENT_2
            | orjson.OPT_NON_STR_KEYS
            | orjson.OPT_OMIT_MICROSECONDS,
        )
        # 写入文件（需要解码为 str）
        with path.open("w", encoding="utf-8") as f:
            f.write(json_bytes.decode("utf-8"))

    def _load_manifest(self, path: Path) -> FreezeManifest:
        """
        从文件加载 manifest。

        Args:
            path: 文件路径

        Returns:
            FreezeManifest 对象

        Raises:
            ValueError: 如果 manifest 格式不正确

        """
        # 使用 orjson 反序列化
        with path.open("rb") as f:
            data = orjson.loads(f.read())

        # 验证必要字段存在
        if "version" not in data or "checksum_type" not in data:
            raise ValueError(
                "Invalid freeze manifest: missing version or checksum_type field. "
                + "This version only supports v2.0 manifests with SHA-256 checksums."
            )

        version = data["version"]
        checksum_type = data["checksum_type"]

        # 验证版本和校验和类型
        if version != "2.0" or checksum_type != "sha256":
            raise ValueError(
                "Invalid freeze manifest: expected v2.0/sha256, "
                + f"got {version}/{checksum_type}"
            )

        return FreezeManifest(
            freeze_id=data["freeze_id"],
            description=data["description"],
            created_at=data["created_at"],
            version=version,
            checksum_type=checksum_type,
            files=data["files"],
        )
