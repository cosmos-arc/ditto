import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HistoryComparisonPanel } from "./history-comparison-panel";

const COMPARISON_PAYLOAD = {
	result_id: "history-comparison:sha256:panel-1",
	strategy_id: "strategy-compare",
	paper_account_id: "paper-1",
	paper_session_id: "paper-session-1",
	manual_account_id: "manual-1",
	model_initial_capital: "100000.00",
	currency: "CNY",
	method: "twr-linked-v1",
	valuation_policy_version: "account-valuation-stale-evidence-v1",
	comparison_policy_version: "common-window-twr-v1",
	status: "comparable",
	empty_reason: null,
	start_date: "2026-03-02",
	end_date: "2026-03-04",
	knowledge_cutoff: "2026-03-04T08:00:00Z",
	publication_cutoff: "2026-03-04T08:00:00Z",
	runs: [
		{
			start_date: "2026-03-02",
			end_date: "2026-03-04",
			point_count: 3,
			points: [
				{
					on_date: "2026-03-02",
					growth: { model: "1", paper: "1", manual: "1" },
					assets: { model: "100000.00", paper: "100000.00", manual: "100000.00" },
				},
				{
					on_date: "2026-03-03",
					growth: { model: "1.1", paper: "1.09", manual: "1.08" },
					assets: { model: "110000.00", paper: "109000.00", manual: "108000.00" },
				},
				{
					on_date: "2026-03-04",
					growth: { model: "1.21", paper: "1.105", manual: "1.168" },
					assets: { model: "121000.00", paper: "110500.00", manual: "116800.00" },
				},
			],
			window_returns: { model: "0.21", paper: "0.105", manual: "0.168" },
		},
	],
	legs: [
		{
			kind: "model",
			result_id: "model-history:sha256:leg-1",
			currency: "CNY",
			empty_reason: null,
			point_count: 3,
			valued_point_count: 3,
			gap_count: 0,
			segment_count: 1,
			first_valued_date: "2026-03-02",
			last_valued_date: "2026-03-04",
			ledger_revision: null,
			target_count: 2,
		},
		{
			kind: "paper",
			result_id: "paper-history:sha256:leg-2",
			currency: "CNY",
			empty_reason: null,
			point_count: 3,
			valued_point_count: 3,
			gap_count: 0,
			segment_count: 1,
			first_valued_date: "2026-03-02",
			last_valued_date: "2026-03-04",
			ledger_revision: { event_count: 3, ledger_hash: "account-ledger:sha256:abc" },
			target_count: null,
		},
		{
			kind: "manual",
			result_id: "manual-history:sha256:leg-3",
			currency: "CNY",
			empty_reason: null,
			point_count: 3,
			valued_point_count: 3,
			gap_count: 0,
			segment_count: 1,
			first_valued_date: "2026-03-02",
			last_valued_date: "2026-03-04",
			ledger_revision: { event_count: 2, ledger_hash: "account-ledger:sha256:def" },
			target_count: null,
		},
	],
};

function jsonResponse(data: unknown, status = 200) {
	return new Response(JSON.stringify({ data }), {
		status,
		headers: { "Content-Type": "application/json" },
	});
}

function stubApi(
	payload: unknown = COMPARISON_PAYLOAD,
	comparisonStatus = 200,
	onComparisonCall?: (call: number, url: URL) => Response | undefined,
) {
	const requests: string[] = [];
	let comparisonCalls = 0;
	const fetchMock = vi.fn<typeof fetch>(async (input) => {
		const href = input instanceof Request ? input.url : String(input);
		requests.push(href);
		const url = new URL(href);
		if (url.pathname === "/api/v1/strategies") {
			// The real endpoint unwraps to a bare StrategyResponse[] array.
			return jsonResponse([
				{
					strategy_id: "strategy-compare",
					name: "比较策略",
					version: 1,
					status: "active",
					lifecycle_state: "active",
					created_at: "2026-01-01T00:00:00Z",
					tags: [],
				},
			]);
		}
		if (url.pathname === "/api/v1/manual/accounts") {
			return jsonResponse({
				accounts: [
					{
						account_id: "manual-1",
						account_kind: "manual",
						account_name: "实盘甲",
						currency: "CNY",
						opened_at: "2026-01-01T00:00:00Z",
					},
				],
			});
		}
		if (url.pathname === "/api/v1/paper/accounts") {
			return jsonResponse({
				accounts: [
					{
						account_id: "paper-1",
						account_kind: "paper",
						account_name: "模拟甲",
						currency: "CNY",
						opened_at: "2026-01-01T00:00:00Z",
					},
				],
			});
		}
		if (url.pathname === "/api/v1/paper/accounts/paper-1/sessions") {
			return jsonResponse({
				sessions: [
					{
						session_id: "paper-session-1",
						account_id: "paper-1",
						strategy_id: "strategy-compare",
						trade_date: "2026-03-02",
						status: "running",
						revision: 1,
						created_at: "2026-03-02T01:00:00Z",
						updated_at: "2026-03-02T01:00:00Z",
					},
				],
			});
		}
		if (url.pathname === "/api/v1/portfolio/history-comparison") {
			comparisonCalls += 1;
			return onComparisonCall?.(comparisonCalls, url) ?? jsonResponse(payload, comparisonStatus);
		}
		throw new Error(`Unhandled mock API request: ${href}`);
	});
	return { fetchMock, requests };
}

function renderPanel(etfAllocationId?: string) {
	return render(
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			<HistoryComparisonPanel etfAllocationId={etfAllocationId} />
		</QueryClientProvider>,
	);
}

async function fillFormAndSubmit(user: ReturnType<typeof userEvent.setup>) {
	await screen.findByText("比较策略");
	await screen.findByText("模拟甲");
	await screen.findByText("实盘甲");
	await screen.findByText(/2026-03-02 · paper-session-1/);
	await user.clear(screen.getByLabelText("比较开始日期"));
	await user.type(screen.getByLabelText("比较开始日期"), "2026-03-02");
	await user.clear(screen.getByLabelText("比较结束日期"));
	await user.type(screen.getByLabelText("比较结束日期"), "2026-03-04");
	await user.clear(screen.getByLabelText("比较知识截止"));
	await user.type(screen.getByLabelText("比较知识截止"), "2026-03-04T08:00:00Z");
	await user.clear(screen.getByLabelText("比较价格快照"));
	await user.type(screen.getByLabelText("比较价格快照"), "snapshot:stock_daily:1");
	await user.click(screen.getByTestId("history-comparison-submit"));
}

afterEach(() => {
	vi.unstubAllGlobals();
	vi.restoreAllMocks();
	window.history.replaceState(null, "", "/");
});

describe("HistoryComparisonPanel", () => {
	it("restores an ETF linked common-window request without deriving history from its target", async () => {
		window.history.replaceState(null, "", "/portfolio?etfAllocation=demo&etfVersion=v1&etfReviewAccount=paper:paper-1");
		const user = userEvent.setup();
		const { fetchMock, requests } = stubApi({ ...COMPARISON_PAYLOAD, strategy_id: "etf-allocation:demo" });
		vi.stubGlobal("fetch", fetchMock);
		const first = renderPanel("demo");
		expect(screen.getByLabelText("Model 策略")).toHaveValue("etf-allocation:demo");
		await fillFormAndSubmit(user);
		await screen.findByTestId("history-comparison-result");
		const saved = new URLSearchParams(window.location.search).get("historyComparison");
		expect(saved).toContain('"source_snapshot_ids":["snapshot:stock_daily:1"]');
		expect(saved).toContain('"origin_version_id":"v1"');
		expect(saved).not.toContain("etfVersion");
		expect(requests.some((href) => href.includes("origin_version_id=v1"))).toBe(true);
		first.unmount();
		const restored = renderPanel("demo");
		await screen.findByTestId("history-comparison-result");
		expect(requests.filter((href) => href.includes("/portfolio/history-comparison"))).toHaveLength(2);
		window.history.replaceState(null, "", window.location.href.replace("etfVersion=v1", "etfVersion=v2"));
		restored.unmount();
		renderPanel("demo");
		expect(screen.queryByTestId("history-comparison-result")).not.toBeInTheDocument();
		expect(requests.filter((href) => href.includes("/portfolio/history-comparison"))).toHaveLength(2);
	});
	it("compares the picked entities and renders the common window with exports", async () => {
		const user = userEvent.setup();
		const { fetchMock, requests } = stubApi();
		vi.stubGlobal("fetch", fetchMock);
		renderPanel();

		await fillFormAndSubmit(user);

		await waitFor(() => {
			expect(screen.getByTestId("history-comparison-result")).toBeInTheDocument();
		});
		const requestUrl = new URL(requests.find((href) => href.includes("/portfolio/history-comparison")) ?? "");
		expect(requestUrl.searchParams.get("strategy_id")).toBe("strategy-compare");
		expect(requestUrl.searchParams.get("paper_account_id")).toBe("paper-1");
		expect(requestUrl.searchParams.get("paper_session_id")).toBe("paper-session-1");
		expect(requestUrl.searchParams.get("manual_account_id")).toBe("manual-1");
		expect(requestUrl.searchParams.get("model_initial_capital")).toBe("100000");

		expect(screen.getByText(/history-comparison:sha256:panel-1/)).toBeInTheDocument();
		expect(screen.getByText("可比区间")).toBeInTheDocument();
		expect(screen.getByTestId("history-comparison-window-return-model")).toHaveTextContent("+21.00%");
		expect(screen.getByTestId("history-comparison-window-return-paper")).toHaveTextContent("+10.50%");
		expect(screen.getByTestId("history-comparison-window-return-manual")).toHaveTextContent("+16.80%");
		expect(screen.getByTestId("history-comparison-line-model").getAttribute("points")).not.toBe("");
		expect(screen.getByText("1.2100")).toBeInTheDocument();
		expect(screen.getByText("121,000.00")).toBeInTheDocument();
		const paperLeg = screen.getByTestId("history-comparison-leg-paper");
		expect(paperLeg).toHaveTextContent("paper-history:sha256:leg-2");
		expect(paperLeg).toHaveTextContent("账本 3@account-ledger:sha256:abc");
	});

	it("downloads a CSV stamped with the backend result identity", async () => {
		const user = userEvent.setup();
		vi.stubGlobal("fetch", stubApi().fetchMock);
		const created: Blob[] = [];
		vi.spyOn(URL, "createObjectURL").mockImplementation((object: Blob | MediaSource) => {
			created.push(object as Blob);
			return "blob:mock";
		});
		vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
		renderPanel();

		await fillFormAndSubmit(user);
		await user.click(await screen.findByTestId("history-comparison-export-csv"));

		expect(created).toHaveLength(1);
		const csv = await (created[0] as Blob).text();
		expect(csv).toContain("# result_id=history-comparison:sha256:panel-1");
		expect(csv).toContain("# method=twr-linked-v1");
		expect(csv).toContain(
			"date,model_growth,paper_growth,manual_growth,benchmark_growth,model_assets,paper_assets,manual_assets",
		);
		expect(csv).toContain("2026-03-04,1.21,1.105,1.168,,121000.00,110500.00,116800.00");
		expect(csv).toContain("window_return,0.21,0.105,0.168,");
	});

	it("declares a benchmark, renders the fourth line, and exports it", async () => {
		const user = userEvent.setup();
		const benchmarkPayload = {
			symbol: "510300",
			type: "price",
			currency: "CNY",
			empty_reason: null,
			runs: [
				{
					start_date: "2026-03-02",
					end_date: "2026-03-04",
					window_return: "0.1",
					points: [
						{ on_date: "2026-03-02", growth: "1" },
						{ on_date: "2026-03-03", growth: null },
						{ on_date: "2026-03-04", growth: "1.1" },
					],
				},
			],
		};
		const { fetchMock, requests } = stubApi({
			...COMPARISON_PAYLOAD,
			benchmark: benchmarkPayload,
		});
		vi.stubGlobal("fetch", fetchMock);
		const created: Blob[] = [];
		vi.spyOn(URL, "createObjectURL").mockImplementation((object: Blob | MediaSource) => {
			created.push(object as Blob);
			return "blob:mock";
		});
		vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
		renderPanel();

		await fillFormAndSubmit(user);
		await user.type(await screen.findByLabelText("比较基准代码"), "510300");
		await user.click(screen.getByTestId("history-comparison-submit"));

		await screen.findByTestId("history-comparison-result");
		const url = new URL(requests.filter((href) => href.includes("/portfolio/history-comparison")).at(-1) ?? "");
		expect(url.searchParams.get("benchmark_symbol")).toBe("510300");
		expect(url.searchParams.get("benchmark_type")).toBe("price");

		const summary = screen.getByTestId("history-comparison-benchmark-summary");
		expect(summary).toHaveTextContent("基准 510300（price）");
		expect(summary).toHaveTextContent("+10.00%");
		// The missing 03-03 price stays a gap: two disjoint polylines, each
		// anchored at its own known day, never a connecting segment.
		const benchmarkLines = screen.getAllByTestId("history-comparison-line-benchmark");
		expect(benchmarkLines).toHaveLength(2);
		expect(benchmarkLines[0]?.getAttribute("points")?.trim().split(" ")).toHaveLength(1);
		expect(benchmarkLines[1]?.getAttribute("points")?.trim().split(" ")).toHaveLength(1);

		await user.click(screen.getByTestId("history-comparison-export-csv"));
		const csv = await (created[0] as Blob).text();
		expect(csv).toContain("# benchmark=510300 type=price");
		expect(csv).toContain("2026-03-04,1.21,1.105,1.168,1.1,121000.00,110500.00,116800.00");
		expect(csv).toContain("window_return,0.21,0.105,0.168,0.1");
	});

	it("reports single common points as assets only", async () => {
		const user = userEvent.setup();
		const singlePoint = {
			...COMPARISON_PAYLOAD,
			status: "single_common_point",
			runs: [
				{
					start_date: "2026-03-02",
					end_date: "2026-03-02",
					point_count: 1,
					points: [COMPARISON_PAYLOAD.runs[0]?.points[0]],
					window_returns: { model: null, paper: null, manual: null },
				},
			],
		};
		vi.stubGlobal("fetch", stubApi(singlePoint).fetchMock);
		renderPanel();

		await fillFormAndSubmit(user);

		expect(await screen.findByText("仅单点共同资产")).toBeInTheDocument();
		expect(screen.getByTestId("history-comparison-single-point-note")).toBeInTheDocument();
		expect(screen.queryByTestId("history-comparison-chart")).not.toBeInTheDocument();
		expect(screen.getByTestId("history-comparison-window-return-model")).toHaveTextContent("—");
	});

	it("explains an incomparable outcome without inventing a window", async () => {
		const user = userEvent.setup();
		const incomparable = {
			...COMPARISON_PAYLOAD,
			status: "incomparable",
			empty_reason: "no_common_valuation_dates",
			runs: [],
		};
		vi.stubGlobal("fetch", stubApi(incomparable).fetchMock);
		renderPanel();

		await fillFormAndSubmit(user);

		expect(await screen.findByText("不可比")).toBeInTheDocument();
		expect(screen.getByText(/no_common_valuation_dates/)).toBeInTheDocument();
		expect(screen.getByText(/没有共同有效估值日/)).toBeInTheDocument();
		expect(screen.queryByTestId("history-comparison-chart")).not.toBeInTheDocument();
	});

	it("renders an error with retry when the comparison fails", async () => {
		const user = userEvent.setup();
		vi.stubGlobal("fetch", stubApi({}, 500).fetchMock);
		renderPanel();

		await fillFormAndSubmit(user);

		const alert = await screen.findByRole("alert");
		expect(alert).toHaveTextContent("共同区间比较失败");
		expect(alert).toHaveTextContent("重试");
	});

	it("degrades PNG export when the environment lacks canvas", async () => {
		const user = userEvent.setup();
		vi.stubGlobal("fetch", stubApi().fetchMock);
		renderPanel();

		await fillFormAndSubmit(user);
		await user.click(await screen.findByTestId("history-comparison-export-png"));

		await waitFor(() => {
			expect(screen.getByText(/当前环境不支持 PNG 导出/)).toBeInTheDocument();
		});
	});

	it("restores both ledger pins and keeps the other pin when one leg replays", async () => {
		const user = userEvent.setup();
		const identity = {
			strategy_id: "etf-allocation:demo",
			paper_account_id: "paper-1",
			paper_session_id: "paper-session-1",
			manual_account_id: "manual-1",
			start_date: "2026-03-02",
			end_date: "2026-03-04",
			model_initial_capital: 100000,
			knowledge_cutoff: "2026-03-04T08:00:00Z",
			publication_cutoff: "2026-03-04T08:00:00Z",
			source_snapshot_ids: ["snapshot:stock_daily:1"],
			origin_version_id: "v1",
			paper_ledger_event_count: 3,
			paper_ledger_hash: "account-ledger:sha256:abc",
			manual_ledger_event_count: 2,
			manual_ledger_hash: "account-ledger:sha256:def",
		};
		window.history.replaceState(
			null,
			"",
			`/portfolio?etfAllocation=demo&etfVersion=v1&etfReviewAccount=paper:paper-1&historyComparisonVersion=v1&historyComparisonAccount=paper:paper-1&historyComparison=${encodeURIComponent(JSON.stringify(identity))}`,
		);
		const { fetchMock, requests } = stubApi({ ...COMPARISON_PAYLOAD, strategy_id: "etf-allocation:demo" });
		vi.stubGlobal("fetch", fetchMock);
		renderPanel("demo");

		// Both restored pins are visible immediately, not just replayable.
		const chips = await screen.findByTestId("history-comparison-pin-chips");
		expect(chips).toHaveTextContent("Paper 钉住 3@account-ledger:sha256:abc");
		expect(chips).toHaveTextContent("Manual 钉住 2@account-ledger:sha256:def");
		await screen.findByTestId("history-comparison-result");
		expect(screen.getByTestId("history-comparison-pin-paper")).toHaveTextContent("解除钉住（解析当前）");

		await user.click(screen.getByTestId("history-comparison-pin-paper"));

		await waitFor(() => {
			const replayUrl = new URL(requests.filter((href) => href.includes("/portfolio/history-comparison")).at(-1) ?? "");
			expect(replayUrl.searchParams.has("paper_ledger_event_count")).toBe(false);
			// Replaying one leg must not drop the other restored pin.
			expect(replayUrl.searchParams.get("manual_ledger_event_count")).toBe("2");
			expect(replayUrl.searchParams.get("manual_ledger_hash")).toBe("account-ledger:sha256:def");
		});
	});

	it("pins a displayed leg revision, replays it, and can unpin back to server resolution", async () => {
		const user = userEvent.setup();
		const { fetchMock, requests } = stubApi();
		vi.stubGlobal("fetch", fetchMock);
		renderPanel();

		await fillFormAndSubmit(user);
		await screen.findByTestId("history-comparison-result");

		await user.click(screen.getByTestId("history-comparison-pin-paper"));

		await waitFor(() => {
			const pinnedUrl = new URL(requests.filter((href) => href.includes("/portfolio/history-comparison")).at(-1) ?? "");
			expect(pinnedUrl.searchParams.get("paper_ledger_event_count")).toBe("3");
			expect(pinnedUrl.searchParams.get("paper_ledger_hash")).toBe("account-ledger:sha256:abc");
			expect(pinnedUrl.searchParams.has("manual_ledger_event_count")).toBe(false);
		});
		expect(await screen.findByText("解除钉住（解析当前）")).toBeInTheDocument();
		const chips = screen.getByTestId("history-comparison-pin-chips");
		expect(chips).toHaveTextContent("Paper 钉住 3@account-ledger:sha256:abc");

		await user.click(screen.getByTestId("history-comparison-pin-paper"));

		await waitFor(() => {
			const unpinnedUrl = new URL(
				requests.filter((href) => href.includes("/portfolio/history-comparison")).at(-1) ?? "",
			);
			expect(unpinnedUrl.searchParams.has("paper_ledger_event_count")).toBe(false);
			expect(unpinnedUrl.searchParams.has("paper_ledger_hash")).toBe(false);
		});
		await waitFor(() => {
			expect(screen.getByTestId("history-comparison-pin-paper")).toHaveTextContent("按此修订重放");
		});
	});

	it("keeps a pinned chip with an escape hatch while the pinned replay errors", async () => {
		const user = userEvent.setup();
		const { fetchMock, requests } = stubApi(COMPARISON_PAYLOAD, 200, (call) =>
			// The pinned replay itself fails (e.g. the ledger moved on).
			call === 2 ? jsonResponse({}, 500) : undefined,
		);
		vi.stubGlobal("fetch", fetchMock);
		renderPanel();

		await fillFormAndSubmit(user);
		await screen.findByTestId("history-comparison-result");
		await user.click(screen.getByTestId("history-comparison-pin-paper"));

		// No result renders, but the pinned chip stays reachable.
		await screen.findByRole("alert");
		expect(screen.queryByTestId("history-comparison-result")).not.toBeInTheDocument();
		expect(screen.getByTestId("history-comparison-pin-chips")).toHaveTextContent("Paper 钉住");

		await user.click(screen.getByTestId("history-comparison-pin-clear-paper"));

		await screen.findByTestId("history-comparison-result");
		const lastUrl = new URL(requests.filter((href) => href.includes("/portfolio/history-comparison")).at(-1) ?? "");
		expect(lastUrl.searchParams.has("paper_ledger_event_count")).toBe(false);
		expect(screen.queryByTestId("history-comparison-pin-chips")).not.toBeInTheDocument();
	});
});
