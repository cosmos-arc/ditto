import { http, HttpResponse, type RequestHandler } from "msw";
import {
	mockEquity,
	mockOrdersSummary,
	mockPositions,
	mockRiskSummary,
	mockSignalDetail,
	mockSignals,
	mockSignalsQueue,
	mockTradingSession,
} from "../fixtures/trading";

export const tradingHandlers: RequestHandler[] = [
	http.get("/api/trading/session", () => {
		return HttpResponse.json(mockTradingSession);
	}),

	http.get("/api/trading/equity", () => {
		return HttpResponse.json({ series: mockEquity });
	}),

	http.get("/api/trading/positions", () => {
		return HttpResponse.json({ positions: mockPositions });
	}),

	http.get("/api/trading/risk/summary", () => {
		return HttpResponse.json(mockRiskSummary);
	}),

	http.get("/api/trading/signals/queue", () => {
		return HttpResponse.json(mockSignalsQueue);
	}),

	http.get("/api/trading/orders/summary", () => {
		return HttpResponse.json(mockOrdersSummary);
	}),

	http.get("/api/trading/signals", ({ request }) => {
		const url = new URL(request.url);
		const tab = url.searchParams.get("tab") ?? "pending";
		const page = Number(url.searchParams.get("page") ?? 1);
		const limit = Number(url.searchParams.get("limit") ?? 20);

		const filtered = mockSignals.items.filter((s) => s.status === tab);
		const start = (page - 1) * limit;
		const paged = filtered.slice(start, start + limit);

		return HttpResponse.json({
			items: paged,
			total: filtered.length,
			page,
			pageSize: limit,
		});
	}),

	http.get("/api/trading/signals/:id", () => {
		return HttpResponse.json(mockSignalDetail);
	}),
];
