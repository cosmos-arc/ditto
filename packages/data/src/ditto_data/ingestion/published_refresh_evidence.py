"""发布后补取的不可变本地观察记录。"""

from hashlib import sha256
from pathlib import Path

import orjson
from ditto_platform.foundation.util.io import atomic_bytes_write


class PublishedRefreshEvidenceStore:
    """内容寻址保留每次结果，迟到成功不能覆盖早先截止失败。"""

    def __init__(self, root: Path) -> None:
        self._root = root

    def record(self, scope: str, report: dict[str, object]) -> None:
        """仅接收两个既定发布检查的记录。"""
        if scope not in {"margin", "fred"}:
            raise ValueError("unsupported published refresh evidence scope")
        payload = orjson.dumps(report, option=orjson.OPT_SORT_KEYS)
        atomic_bytes_write(
            payload, self._root / scope / f"{sha256(payload).hexdigest()}.json"
        )
