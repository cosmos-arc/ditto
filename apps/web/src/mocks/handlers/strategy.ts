import { HttpResponse, http, type RequestHandler } from "msw";
import { mockFactorLibrary, mockStrategyDetail, mockStrategyVersions } from "../fixtures/strategy";
import {
	mockNodeDescriptorList,
	mockSpecDiffDto,
	mockSpecValidationDto,
	mockStrategyDetailDto,
	mockStrategyList,
	mockStrategyVersionList,
} from "../fixtures/strategy-live";

export const strategyHandlers: RequestHandler[] = [
	// === legacy prototype handlers（未迁移组件消费，组件迁移完成后清理）===
	http.get("/api/strategies/:id", () => HttpResponse.json(mockStrategyDetail)),
	http.get("/api/strategies/:id/versions", () => HttpResponse.json(mockStrategyVersions)),
	http.get("/api/factor-library", ({ request }) => {
		const url = new URL(request.url);
		const page = Number(url.searchParams.get("page") ?? 1);
		const pageSize = Number(url.searchParams.get("pageSize") ?? 20);
		const start = (page - 1) * pageSize;
		const items = mockFactorLibrary.items.slice(start, start + pageSize);
		return HttpResponse.json({ items, total: mockFactorLibrary.total, page, pageSize });
	}),

	// === R3 live-shape handlers（/api/v1/...，generated DTO + {data} 信封）===
	http.get("/api/v1/strategies", () =>
		HttpResponse.json({
			data: mockStrategyList,
			pagination: { total: mockStrategyList.length, limit: 50, offset: 0, has_more: false },
		}),
	),
	http.get("/api/v1/strategies/:id", ({ params }) => {
		const id = String(params.id);
		const found = mockStrategyList.find((s) => s.strategy_id === id) ?? mockStrategyDetailDto;
		return HttpResponse.json({ data: found });
	}),
	http.get("/api/v1/strategies/:id/versions", () => HttpResponse.json({ data: mockStrategyVersionList })),
	http.get("/api/v1/strategies/:id/versions/:version/diff", () => HttpResponse.json({ data: mockSpecDiffDto })),
	http.post("/api/v1/strategies/:id/versions/:version/validate", () =>
		HttpResponse.json({ data: mockSpecValidationDto }),
	),
	http.get("/api/v1/research/node-descriptors", () => HttpResponse.json({ data: mockNodeDescriptorList })),
];
