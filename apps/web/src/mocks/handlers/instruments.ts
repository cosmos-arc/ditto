import { HttpResponse, http, type RequestHandler } from "msw";

const INSTRUMENTS = [
	{
		asset_class: "stock",
		exchange: "SSE",
		instrument_id: 1000001,
		is_active: true,
		list_date: "2001-08-27",
		name: "贵州茅台",
		ticker: "600519",
	},
	{
		asset_class: "stock",
		exchange: "SZSE",
		instrument_id: 1000002,
		is_active: true,
		list_date: "2018-06-11",
		name: "宁德时代",
		ticker: "300750",
	},
	{
		asset_class: "stock",
		exchange: "SZSE",
		instrument_id: 1000003,
		is_active: true,
		list_date: "2011-06-30",
		name: "比亚迪",
		ticker: "002594",
	},
	{
		asset_class: "etf",
		exchange: "SSE",
		instrument_id: 1000004,
		is_active: true,
		list_date: "2012-05-28",
		name: "沪深300ETF",
		ticker: "510300",
	},
] as const;

export const instrumentsHandlers: RequestHandler[] = [
	http.get("/api/v1/metadata/etf-reference-snapshots", () => HttpResponse.json({ data: [] })),
	http.get("/api/v1/metadata/etf-candidates", () => HttpResponse.json({ data: [] })),
	http.get("/api/v1/metadata/instruments", ({ request }) => {
		const query = new URL(request.url).searchParams;
		const assetClass = query.get("asset_class");
		const exchange = query.get("exchange");
		const isActive = query.get("is_active");
		const offset = Number(query.get("offset") ?? 0);
		const limit = Number(query.get("limit") ?? 100);
		const filtered = INSTRUMENTS.filter(
			(item) =>
				(assetClass == null || item.asset_class === assetClass) &&
				(exchange == null || item.exchange === exchange) &&
				(isActive == null || item.is_active === (isActive === "true")),
		);
		return HttpResponse.json({
			data: filtered.slice(offset, offset + limit),
			pagination: {
				has_more: offset + limit < filtered.length,
				limit,
				offset,
				total: filtered.length,
			},
		});
	}),

	http.get("/api/v1/metadata/instruments/:id", ({ params }) => {
		const instrumentId = Number(params["id"]);
		const instrument = INSTRUMENTS.find(
			(item) => item.instrument_id === instrumentId || Number(item.ticker) === instrumentId,
		);
		if (!instrument) return HttpResponse.json({ detail: "instrument not found" }, { status: 404 });
		return HttpResponse.json({ data: { ...instrument, instrument_id: instrumentId } });
	}),

	http.post("/api/v1/market/bars", async ({ request }) => {
		const body = (await request.json()) as { instrument_ids?: number[] };
		const instrumentId = body.instrument_ids?.[0] ?? 1000001;
		return HttpResponse.json({
			data: [
				{
					amount: 5632000000,
					close: 1750.2,
					high: 1768.8,
					instrument_id: instrumentId,
					low: 1738.4,
					open: 1744.6,
					trade_date: "2026-03-10",
					turnover_rate: 0.42,
					volume: 3210000,
				},
				{
					amount: 5490000000,
					close: 1746.3,
					high: 1760,
					instrument_id: instrumentId,
					low: 1732.1,
					open: 1752,
					trade_date: "2026-03-09",
					turnover_rate: 0.4,
					volume: 3140000,
				},
			],
		});
	}),

	http.post("/api/v1/market/indicator-series", async ({ request }) => {
		const body = (await request.json()) as { indicators?: string[]; ma_windows?: number[] };
		const trade_dates = ["2026-03-09", "2026-03-10"];
		const series: Array<{ name: string; window: number | null; values: Array<number | null> }> = [];
		for (const indicator of body.indicators ?? []) {
			if (indicator === "ma") {
				for (const window of body.ma_windows ?? [5, 20, 60]) {
					series.push({ name: `ma_${window}`, window, values: [null, 1748.25] });
				}
			}
			if (indicator === "macd") {
				series.push({ name: "macd", window: 26, values: [null, 1.2] });
				series.push({ name: "macd_signal", window: 26, values: [null, 0.8] });
				series.push({ name: "macd_histogram", window: 26, values: [null, 0.4] });
			}
			if (indicator === "rsi") {
				series.push({ name: "rsi", window: 14, values: [null, 55.5] });
			}
			if (indicator === "atr") {
				series.push({ name: "atr", window: 14, values: [null, 12.3] });
			}
			if (indicator === "donchian") {
				series.push({ name: "donchian_high", window: 20, values: [null, 1760] });
				series.push({ name: "donchian_low", window: 20, values: [null, 1732.1] });
			}
		}
		return HttpResponse.json({
			data: {
				instrument_id: 1000001,
				adjustment: "none",
				registry_version: "technical-indicator-registry.v1",
				trade_dates: trade_dates,
				series,
			},
		});
	}),

	http.post("/api/v1/market/etf-nav", async () => {
		// 本地净值库对 mock 标的无可得数据：空 points 驱动诚实降级态
		return HttpResponse.json({ data: { instrument_id: 1000001, points: [] } });
	}),
];
