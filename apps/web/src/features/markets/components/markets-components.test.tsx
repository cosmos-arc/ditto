import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { WatchlistPage } from "@/workflows/market-pages";

/** 等待锚点格从"解析中"落到稳定文案（真实摄取结果或未解析）。 */
async function waitForAnchorDate(anchor: HTMLElement, expected: string): Promise<boolean> {
	await waitFor(() => {
		if (!anchor.textContent?.includes(expected)) throw new Error(`锚点未落到 ${expected}: ${anchor.textContent}`);
	});
	return true;
}

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

beforeEach(() => localStorage.clear());

describe("WatchlistPage", () => {
	it("自选列表默认为空且明确仅保存在本机", async () => {
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText("尚未添加标的")).resolves.toBeInTheDocument();
		await expect(screen.findByText(/仅保存在当前浏览器/)).resolves.toBeInTheDocument();
	});

	it("按名称检索并加入自选，刷新（重挂载）后按精确身份重开", async () => {
		const user = userEvent.setup();
		const { unmount } = render(<WatchlistPage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "添加标的" }));
		await user.type(screen.getByLabelText("搜索代码或名称"), "茅台");
		await user.click(screen.getByRole("button", { name: "检索" }));
		const candidate = await screen.findByRole("button", { name: /加入自选 贵州茅台/ });
		await user.click(candidate);
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();

		// 重挂载模拟刷新重开：localStorage 持久化 + 每个对象按精确身份重新解析。
		unmount();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		expect(screen.getByText(/600519 · SSE/)).toBeInTheDocument();
	});

	it("按代码检索也能命中同一标的", async () => {
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "添加标的" }));
		await user.type(screen.getByLabelText("搜索代码或名称"), "300750");
		await user.click(screen.getByRole("button", { name: "检索" }));
		await expect(screen.findByRole("button", { name: /加入自选 宁德时代/ })).resolves.toBeInTheDocument();
	});

	it("无命中时明确提示，不产生假结果", async () => {
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "添加标的" }));
		await user.type(screen.getByLabelText("搜索代码或名称"), "不存在的东西");
		await user.click(screen.getByRole("button", { name: "检索" }));
		await expect(screen.findByText(/没有匹配的标的/)).resolves.toBeInTheDocument();
	});

	it("检索失败后同词重提交真实重取并恢复", async () => {
		server.use(http.get("/api/v1/metadata/instruments", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "添加标的" }));
		await user.type(screen.getByLabelText("搜索代码或名称"), "茅台");
		await user.click(screen.getByRole("button", { name: "检索" }));
		await expect(screen.findByText(/检索失败/)).resolves.toBeInTheDocument();

		// 同一个词再次提交：不能停在错误态，必须重新发起真实请求。
		server.resetHandlers();
		await user.click(screen.getByRole("button", { name: "检索" }));
		await expect(screen.findByRole("button", { name: /加入自选 贵州茅台/ })).resolves.toBeInTheDocument();
	});

	it("超过一页的命中展示总数与截断证据，并可加载全部", async () => {
		const matches = Array.from({ length: 25 }, (_, index) => ({
			asset_class: "stock",
			exchange: "SSE",
			instrument_id: 2_000_000 + index,
			is_active: true,
			list_date: "2001-08-27",
			name: `多样本股${String(index + 1).padStart(2, "0")}`,
			ticker: `6100${String(index + 1).padStart(2, "0")}`,
		}));
		server.use(
			http.get("/api/v1/metadata/instruments", ({ request }) => {
				const query = new URL(request.url).searchParams;
				const offset = Number(query.get("offset") ?? 0);
				const limit = Number(query.get("limit") ?? 100);
				return HttpResponse.json({
					data: matches.slice(offset, offset + limit),
					pagination: { has_more: offset + limit < 25, limit, offset, total: 25 },
				});
			}),
		);
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "添加标的" }));
		await user.type(screen.getByLabelText("搜索代码或名称"), "多样本股");
		await user.click(screen.getByRole("button", { name: "检索" }));

		// 截断证据：总数与已加载数量明示，不静默只给前 20。
		await expect(screen.findByText(/共 25 项 · 已加载 20/)).resolves.toBeInTheDocument();
		expect(screen.getAllByRole("button", { name: /^加入自选/ })).toHaveLength(20);

		await user.click(screen.getByRole("button", { name: "加载更多" }));
		await expect(screen.getAllByRole("button", { name: /^加入自选/ })).toHaveLength(25);
		await expect(screen.findByText(/共 25 项 · 已加载 25/)).resolves.toBeInTheDocument();
	});

	it("未知对象不静默消失：目录未找到的 ID 明确展示并保留", async () => {
		localStorage.setItem("ditto.market-watchlist.v1", "[9999999]");
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText(/目录中未找到/)).resolves.toBeInTheDocument();
		expect(screen.getByText(/9999999/)).toBeInTheDocument();
		await expect(screen.findByRole("button", { name: "移除 未知标的 9999999" })).resolves.toBeInTheDocument();
	});

	it("已退出对象保留展示并标注退出状态", async () => {
		localStorage.setItem("ditto.market-watchlist.v1", "[1000005]");
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText("退市示例")).resolves.toBeInTheDocument();
		expect(screen.getByText("已退出")).toBeInTheDocument();
	});

	it("活跃自选展示真实最近收盘与涨跌，链接携带该观察日进入图表", async () => {
		localStorage.setItem("ditto.market-watchlist.v1", "[1000001]");
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		// 行情列来自真实 market/chart 合同（mock 两根日 K：03-09 收 1746.3、03-10 收 1750.2）。
		await expect(screen.findByText("1750.20")).resolves.toBeInTheDocument();
		expect(screen.getByText(/^\+3\.90/)).toBeInTheDocument();
		expect(screen.getByText(/\+0\.22%/)).toBeInTheDocument();
		expect(screen.getByText(/行情日 2026-03-10/)).toBeInTheDocument();
		// 表（自选行情列）与图（标的 K 线）共用同一观察日与同一收盘数字。
		expect(screen.getByRole("link", { name: "贵州茅台" })).toHaveAttribute(
			"href",
			"/instruments/1000001?tab=chart&observeDate=2026-03-10",
		);
	});

	it("摘要以日历数据集真实摄取结果显示最近完整交易日锚点", async () => {
		localStorage.setItem("ditto.market-watchlist.v1", "[1000001]");
		render(<WatchlistPage />, { wrapper: wrapper() });
		const anchor = await screen.findByTestId("watchlist-anchor");
		expect(anchor).toHaveTextContent("最近完整交易日");
		await expect(waitForAnchorDate(anchor, "2026-09-30")).resolves.toBe(true);
	});

	it("行情读取失败不锁死对象：行内明确失败并可重试恢复", async () => {
		server.use(http.post("/api/v1/market/chart", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
		localStorage.setItem("ditto.market-watchlist.v1", "[1000001]");
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		await expect(screen.findByText(/行情读取失败/)).resolves.toBeInTheDocument();
		// 对象本身没有被封死：移除/进入链接仍可用，行情可在行内重试。
		expect(screen.getByRole("link", { name: "贵州茅台" })).toHaveAttribute("href", "/instruments/1000001");
		server.resetHandlers();
		await user.click(screen.getByRole("button", { name: "重试行情 贵州茅台" }));
		await expect(screen.findByText("1750.20")).resolves.toBeInTheDocument();
	});

	it("本地行情库无可见日 K 时明确「行情不可得」，不用静态值顶替", async () => {
		server.use(
			http.post("/api/v1/market/chart", () =>
				HttpResponse.json({
					data: {
						instrument_id: 1000001,
						period: "daily",
						adjustment: "none",
						as_of: "2026-03-10T08:00:00Z",
						knowledge_cutoff: "2026-03-10T08:00:00Z",
						publication_cutoff: "2026-03-10T08:00:00Z",
						timezone: "Asia/Shanghai",
						calendar_snapshot_ids: [],
						source_snapshot_ids: [],
						sources: [],
						latest_price_date: null,
						stale_reason: null,
						missing_sessions: [],
						bars: [],
					},
				}),
			),
		);
		localStorage.setItem("ditto.market-watchlist.v1", "[1000001]");
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		await expect(screen.findByText("行情不可得")).resolves.toBeInTheDocument();
		expect(screen.queryByText(/^\d+\.\d{2}$/)).not.toBeInTheDocument();
		// 无行情日的对象进入工作面仍可用（不带观察日锚点）。
		expect(screen.getByRole("link", { name: "贵州茅台" })).toHaveAttribute("href", "/instruments/1000001");
	});

	it("日历状态不可得时锚点如实显示未解析，行情列仍可用", async () => {
		server.use(http.get("/api/v1/ingestion/status", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
		localStorage.setItem("ditto.market-watchlist.v1", "[1000001]");
		render(<WatchlistPage />, { wrapper: wrapper() });
		const anchor = await screen.findByTestId("watchlist-anchor");
		expect(anchor).toHaveTextContent("最近完整交易日");
		await expect(waitForAnchorDate(anchor, "未解析")).resolves.toBe(true);
		await expect(screen.findByText("1750.20")).resolves.toBeInTheDocument();
	});

	it("解析失败的对象保留并可重试恢复", async () => {
		server.use(
			http.get("/api/v1/metadata/instruments/1000002", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
		);
		localStorage.setItem("ditto.market-watchlist.v1", "[1000002]");
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText(/解析失败/)).resolves.toBeInTheDocument();
		server.resetHandlers();
		await user.click(screen.getByRole("button", { name: "重试" }));
		await expect(screen.findByText("宁德时代")).resolves.toBeInTheDocument();
	});

	it("移除单个自选后清单更新", async () => {
		localStorage.setItem("ditto.market-watchlist.v1", "[1000001]");
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "移除 贵州茅台" }));
		await expect(screen.findByText("尚未添加标的")).resolves.toBeInTheDocument();
	});

	it("批量删除 overlay 明确只清空本机清单", async () => {
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "批量删除" }));
		expect(screen.getByRole("dialog", { name: "批量删除自选" })).toHaveTextContent("localStorage");
	});
});
