"""资金纠偏的不可变资格清单；原投影与来源 payload 保留供显式审计重放。"""

from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any

import orjson
import polars as pl
from ditto_platform.foundation.util.io import atomic_bytes_write

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader

CAPITAL_RULE_VERSION = "capital-kd-v2"


def publish_correction(data_root: Path, report: dict[str, Any]) -> str:
    """先持久化资格撤销及影响清单，再写替代投影；中断时宁缺不泄漏。"""
    payload = orjson.dumps(report, option=orjson.OPT_SORT_KEYS)
    checksum = sha256(payload).hexdigest()
    # 完整事实清单只供审计；查询仅加载按日期/旧知识日收敛的资格规则。
    audit = data_root / "operations" / "capital-corrections" / f"{checksum}.json"
    atomic_bytes_write(payload, audit)
    rules = {
        "dataset": report["dataset"],
        "rule_version": CAPITAL_RULE_VERSION,
        "impact_checksum": checksum,
        "invalidated": sorted(
            {
                (item["trade_date"], item["old_knowledge_date"])
                for item in report["impacts"]
            }
        ),
    }
    rule_payload = orjson.dumps(rules, option=orjson.OPT_SORT_KEYS)
    rule_checksum = sha256(rule_payload).hexdigest()
    path = (
        data_root
        / "capital"
        / "corrections"
        / report["dataset"]
        / f"{rule_checksum}.json"
    )
    atomic_bytes_write(rule_payload, path)
    return checksum


def eligible_versions(
    frame: pl.DataFrame, data_root: Path, dataset: str
) -> pl.DataFrame:
    """普通读取排除明确撤销的完整旧版本键，不能先按最大知识日选择。"""
    if frame.is_empty():
        return frame
    for path in sorted(
        (data_root / "capital" / "corrections" / dataset).glob("*.json")
    ):
        payload = path.read_bytes()
        if sha256(payload).hexdigest() != path.stem:
            raise ValueError("capital correction checksum mismatch")
        report = orjson.loads(payload)
        if (
            report["dataset"] != dataset
            or report["rule_version"] != CAPITAL_RULE_VERSION
        ):
            raise ValueError("unsupported capital correction identity")
        keys = ["trade_date", "knowledge_date"]
        invalid = pl.DataFrame(report["invalidated"], schema=keys, orient="row").cast(
            {key: frame.schema[key] for key in keys}
        )
        frame = frame.join(invalid, on=keys, how="anti", maintain_order="left")
    return frame


class CapitalVersionReader(ParquetDatasetReader):
    """北向两个数据集共用纠偏资格读取，原文件和快照重放不受修改。"""

    def read(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        filters: pl.Expr | Sequence[pl.Expr] | None = None,
    ) -> pl.DataFrame:
        """读取具有普通消费资格的资金版本。"""
        frame = super().read(instrument_ids, start_date, end_date, filters)
        return eligible_versions(
            frame, self.data_root, self._dataset.removeprefix("capital/")
        )

    def count(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        filters: pl.Expr | Sequence[pl.Expr] | None = None,
    ) -> int:
        """计数与普通读取保持相同资格。"""
        return self.read(instrument_ids, start_date, end_date, filters).height
