"""#623 失败分类单元测试：取数错误码细分 + 错误码词汇闭合守卫."""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import pytest
from ditto_application.processes.ingestion.result_handler import (
    IngestionResultHandler,
    classified_fetch_error_code,
)
from ditto_data.errors import (
    AuthError,
    NetworkError,
    SourceAuthenticationError,
    SourceFetchError,
    SourceRateLimitError,
)
from ditto_data.ingestion.ingestion_log_store import IngestionLogStore
from ditto_data.models.ingestion import (
    INGESTION_ERROR_CODE_KINDS,
    IngestionFailureKind,
    IngestionLog,
    IngestionStatus,
)


class _RecordingLogStore:
    """记录 save_log 调用的最小桩（不触 SQLite）。"""

    def __init__(self) -> None:
        self.logs: list[IngestionLog] = []

    def save_log(self, log: IngestionLog) -> IngestionLog:
        self.logs.append(log)
        return log


class TestClassifiedFetchErrorCode:
    """取数失败按底层原因细分 error_code（#623）。"""

    def test_rate_limit(self) -> None:
        error = SourceFetchError(
            message="Tushare API 限流",
            source="tushare",
            cause=SourceRateLimitError(source="tushare"),
        )
        assert classified_fetch_error_code(error) == "RATE_LIMIT"

    def test_network_error(self) -> None:
        error = SourceFetchError(
            message="连接超时",
            source="tushare",
            cause=NetworkError(message="timeout", source="tushare"),
        )
        assert classified_fetch_error_code(error) == "NETWORK_ERROR"

    def test_auth_error(self) -> None:
        error = SourceFetchError(
            message="token 无效",
            source="tushare",
            cause=SourceAuthenticationError(source="tushare"),
        )
        assert classified_fetch_error_code(error) == "SOURCE_AUTH_ERROR"

    def test_legacy_auth_error(self) -> None:
        error = SourceFetchError(
            message="token 无效",
            source="tushare",
            cause=AuthError(message="invalid token", source="tushare"),
        )
        assert classified_fetch_error_code(error) == "SOURCE_AUTH_ERROR"

    def test_generic_fetch_error(self) -> None:
        error = SourceFetchError(message="供应商 5xx", source="tushare")
        assert classified_fetch_error_code(error) == "FETCH_ERROR"

    def test_generic_cause(self) -> None:
        error = SourceFetchError(
            message="供应商 5xx",
            source="tushare",
            cause=ValueError("upstream"),
        )
        assert classified_fetch_error_code(error) == "FETCH_ERROR"

    def test_tushare_permission_code_is_permanent(self) -> None:
        """50101（接口无权限，#517-#523 裁决线）不得折叠进瞬态 FETCH_ERROR。"""
        error = SourceFetchError(
            message="抱歉, 您没有访问该接口的权限",
            source="tushare",
            details={"code": 50101},
        )
        code = classified_fetch_error_code(error)
        assert code == "SOURCE_PERMISSION_DENIED"
        assert INGESTION_ERROR_CODE_KINDS[code] is IngestionFailureKind.PERMANENT

    def test_unadjudicated_tushare_codes_stay_fetch_error(self) -> None:
        """未裁决语义的结构化码保持 FETCH_ERROR 瞬态（attempts 兜底）。"""
        error = SourceFetchError(
            message="业务错误",
            source="tushare",
            details={"code": 9999},
        )
        assert classified_fetch_error_code(error) == "FETCH_ERROR"


class TestHandleFetchErrorPersistsClassifiedCode:
    """handle_fetch_error 落库细分码，供重试选择按瞬态/永久分流。"""

    @staticmethod
    def _handler() -> tuple[IngestionResultHandler, _RecordingLogStore]:
        store = _RecordingLogStore()
        # 记录桩只为断言 save_log 入参，运行时形状与 IngestionLogStore 一致。
        handler = IngestionResultHandler(
            cast("IngestionLogStore | None", store), "tushare"
        )
        return handler, store

    def test_rate_limit_persisted_as_transient(self) -> None:
        handler, store = self._handler()
        result = handler.handle_fetch_error(
            "etf_nav",
            "2026-10-29",
            SourceFetchError(
                message="Tushare API 限流 (API: etf_basic)",
                source="tushare",
                cause=SourceRateLimitError(source="tushare"),
            ),
        )
        assert result.error == "RATE_LIMIT"
        assert store.logs[0].error_code == "RATE_LIMIT"
        assert store.logs[0].status is IngestionStatus.FAIL
        assert INGESTION_ERROR_CODE_KINDS["RATE_LIMIT"] is (
            IngestionFailureKind.TRANSIENT
        )

    def test_generic_fetch_error_persisted(self) -> None:
        handler, store = self._handler()
        handler.handle_fetch_error(
            "stock_daily",
            "2026-10-29",
            SourceFetchError(message="供应商 5xx", source="tushare"),
        )
        assert store.logs[0].error_code == "FETCH_ERROR"


class TestErrorCodeVocabularyClosure:
    """
    错误码词汇闭合守卫（#623）。

    摄取链落库/返回的 error_code 字面量必须登记在
    INGESTION_ERROR_CODE_KINDS——新码未登记时分类 fail-closed 归
    permanent，自动重试静默跳过；本守卫强制新增码显式声明分类。
    """

    _SOURCE_FILES = (
        "packages/application/src/ditto_application/processes/ingestion/result_handler.py",
        "packages/application/src/ditto_application/processes/ingestion/post_ingest.py",
        "packages/application/src/ditto_application/processes/ingestion/evidence_commit.py",
        "apps/backend/src/ditto_apps/jobs/tasks/t0_meta.py",
    )
    # 覆盖三类发射点：error/error_code 赋值、结果 dict 字面量、
    # classified_fetch_error_code 的 return。
    _LITERAL_RE = re.compile(
        r'(?:error(?:_code)?\s*=\s*|"error(?:_code)":\s*|return )"([A-Z][A-Z0-9_]+)"'
    )

    def test_all_emitted_codes_are_classified(self) -> None:
        repo_root = Path(__file__).resolve().parents[6]
        emitted: set[str] = set()
        for relative in self._SOURCE_FILES:
            source = (repo_root / relative).read_text(encoding="utf-8")
            emitted.update(self._LITERAL_RE.findall(source))
        assert emitted, "守卫扫描必须命中至少一个错误码字面量"
        unclassified = emitted - set(INGESTION_ERROR_CODE_KINDS)
        assert not unclassified, (
            f"未登记分类的错误码: {sorted(unclassified)}; "
            "请在 ditto_data.models.ingestion.INGESTION_ERROR_CODE_KINDS 声明"
        )


class TestIngestionLogStoreInterface:
    """补偿发现依赖的 store 查询存在于日志 store 公共接口。"""

    def test_list_failed_error_groups_on_store(self) -> None:
        assert hasattr(IngestionLogStore, "list_failed_error_groups")


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])
