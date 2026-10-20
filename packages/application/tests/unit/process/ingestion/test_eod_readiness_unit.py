"""EOD readiness verification against ledger-attested window evidence."""

from datetime import date

from ditto_application.processes.ingestion.eod_readiness import (
    EodReadinessVerifier,
)
from ditto_application.processes.selection.assemble_facts import SnapshotWindow

_DAY = date(2026, 10, 20)


class _FakeIndex:
    def __init__(self, windows_by_dataset):
        self._windows = windows_by_dataset

    def snapshot_ids(self, dataset_id):
        return tuple(window.snapshot_id for window in self._windows[dataset_id])

    def windows(self, dataset_id):
        return self._windows[dataset_id]


def _windows(dataset, *spec):
    return tuple(
        SnapshotWindow(f"snapshot:tushare:{dataset}:sha256:{i}", start, end, rows)
        for i, (start, end, rows) in enumerate(spec)
    )


def test_ready_day_passes_without_refetch():
    index = _FakeIndex(
        {
            "stock_daily": _windows("stock_daily", (date(2026, 10, 8), _DAY, 39054)),
        }
    )
    calls = []
    report = EodReadinessVerifier(
        index, reingest=lambda dataset, day: calls.append((dataset, day))
    ).verify(datasets=("stock_daily",), trade_date=_DAY)
    assert report.missing == ()
    assert report.refetched == ()
    assert calls == []
    assert report.datasets[0].attested_through == _DAY


def test_missing_day_refetches_once_and_recovers():
    state = {
        "stock_status": _windows(
            "stock_status", (date(2026, 10, 8), date(2026, 10, 16), 39054)
        )
    }
    index = _FakeIndex(state)
    calls = []

    def reingest(dataset, day):
        calls.append((dataset, day))
        # 重拉落地真实行数的新快照（#583 切片 B 之前这里只会是空观察）。
        state["stock_status"] = (
            *state["stock_status"],
            SnapshotWindow(
                "snapshot:tushare:stock_status:sha256:new",
                date(2026, 10, 19),
                date(2026, 10, 20),
                5579,
            ),
        )

    report = EodReadinessVerifier(index, reingest=reingest).verify(
        datasets=("stock_status",), trade_date=_DAY
    )
    assert report.missing == ()
    assert report.refetched == ("stock_status",)
    assert calls == [("stock_status", "2026-10-20")]


def test_empty_observation_never_counts_and_alert_gap_remains():
    index = _FakeIndex(
        {
            "stock_status": _windows(
                # 同晚 0 行历史空观察 + 更早的真实行窗口。
                "stock_status",
                (date(2026, 10, 8), date(2026, 10, 16), 39054),
                (_DAY, _DAY, 0),
            )
        }
    )
    report = EodReadinessVerifier(index).verify(
        datasets=("stock_status",), trade_date=_DAY
    )
    assert report.missing == ("stock_status",)
    assert report.datasets[0].attested_through == date(2026, 10, 16)


def test_no_retry_mode_reports_gap_without_reingest():
    index = _FakeIndex({"adj_factor": _windows("adj_factor")})
    calls = []
    report = EodReadinessVerifier(
        index, reingest=lambda dataset, day: calls.append((dataset, day))
    ).verify(datasets=("adj_factor",), trade_date=_DAY, retry=False)
    assert report.missing == ("adj_factor",)
    assert calls == []
