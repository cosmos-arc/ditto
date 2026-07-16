import { http, HttpResponse, type RequestHandler } from "msw";
import {
	mockStrategyDetail,
	mockStrategyVersions,
	mockFactorLibrary,
} from "../fixtures/strategy";

export const strategyHandlers: RequestHandler[] = [
	http.get("/api/strategies/:id", () => {
		return HttpResponse.json(mockStrategyDetail);
	}),

	http.get("/api/strategies/:id/versions", () => {
		return HttpResponse.json(mockStrategyVersions);
	}),

	http.get("/api/factor-library", ({ request }) => {
		const url = new URL(request.url);
		const page = Number(url.searchParams.get("page") ?? 1);
		const pageSize = Number(url.searchParams.get("pageSize") ?? 20);
		const start = (page - 1) * pageSize;
		const items = mockFactorLibrary.items.slice(start, start + pageSize);

		return HttpResponse.json({
			items,
			total: mockFactorLibrary.total,
			page,
			pageSize,
		});
	}),
];
