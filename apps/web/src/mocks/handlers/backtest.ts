import { HttpResponse, http, type RequestHandler } from "msw";
import {
	mockBacktestAudit,
	mockBacktestBenchmark,
	mockBacktestNav,
	mockBacktestReport,
	mockBacktestRuns,
	mockBacktestTrades,
} from "../fixtures/backtest";

export const backtestHandlers: RequestHandler[] = [
	http.get("/api/v1/backtests/runs", () => HttpResponse.json({ data: mockBacktestRuns })),
	http.get("/api/v1/backtests/runs/:runId", ({ params }) => {
		const run = mockBacktestRuns.find((row) => row.run_id === params.runId);
		return run
			? HttpResponse.json({ data: run })
			: HttpResponse.json({ detail: "run not found", error_code: "BACKTEST_RUN_NOT_FOUND" }, { status: 404 });
	}),
	http.get("/api/v1/backtests/runs/:runId/report", ({ params }) =>
		params.runId === "bt-001"
			? HttpResponse.json({ data: mockBacktestReport })
			: HttpResponse.json({ detail: "report not found", error_code: "BACKTEST_REPORT_NOT_FOUND" }, { status: 404 }),
	),
	http.get("/api/v1/backtests/runs/:runId/nav", ({ params }) =>
		params.runId === "bt-001"
			? HttpResponse.json({ data: mockBacktestNav })
			: HttpResponse.json({ detail: "nav not found", error_code: "BACKTEST_NAV_NOT_FOUND" }, { status: 404 }),
	),
	http.get("/api/v1/backtests/runs/:runId/benchmark", ({ params }) =>
		params.runId === "bt-001"
			? HttpResponse.json({ data: mockBacktestBenchmark })
			: HttpResponse.json(
					{ detail: "benchmark not found", error_code: "BACKTEST_BENCHMARK_NOT_FOUND" },
					{ status: 404 },
				),
	),
	http.get("/api/v1/backtests/runs/:runId/trades", ({ params }) =>
		params.runId === "bt-001"
			? HttpResponse.json({ data: mockBacktestTrades })
			: HttpResponse.json({ detail: "trades not found", error_code: "BACKTEST_TRADES_NOT_FOUND" }, { status: 404 }),
	),
	http.get("/api/v1/backtests/runs/:runId/audit", ({ params }) =>
		params.runId === "bt-001"
			? HttpResponse.json({ data: mockBacktestAudit })
			: HttpResponse.json({ detail: "audit not found", error_code: "BACKTEST_AUDIT_NOT_FOUND" }, { status: 404 }),
	),
];
