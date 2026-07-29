import { HttpResponse, http, type RequestHandler } from "msw";
import {
	mockActivePointerDto,
	mockNodeDescriptorList,
	mockSpecDiffDto,
	mockSpecValidationDto,
	mockStrategyDetailDto,
	mockStrategyList,
	mockStrategyVersionList,
	mockVersionStateDto,
} from "../fixtures/strategy-live";

/**
 * Strategy feature MSW handlers（R3 live-shape，generated DTO + `{data}` 信封）。
 *
 * 覆盖策略列表/详情/版本/active/diff/validate + T20 治理 mutations。旧 prototype handler
 * （`/api/strategies/*` 无 v1、`/api/factor-library`）与旧 fixture 已随 factor-browser 一并清理。
 */
export const strategyHandlers: RequestHandler[] = [
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
	http.get("/api/v1/strategies/:id/active", () => HttpResponse.json({ data: mockActivePointerDto })),
	http.get("/api/v1/strategies/:id/versions/:version/diff", () => HttpResponse.json({ data: mockSpecDiffDto })),
	http.post("/api/v1/strategies/:id/versions/:version/validate", () =>
		HttpResponse.json({ data: mockSpecValidationDto }),
	),

	// === T20 治理 mutations（mock 回固定状态；reactivate 回 active pointer）===
	http.post("/api/v1/strategies/:id/versions/:version/submit-review", () =>
		HttpResponse.json({ data: mockVersionStateDto }),
	),
	http.post("/api/v1/strategies/:id/versions/:version/approve", () => HttpResponse.json({ data: mockVersionStateDto })),
	http.post("/api/v1/strategies/:id/versions/:version/reject", () => HttpResponse.json({ data: mockVersionStateDto })),
	http.post("/api/v1/strategies/:id/versions/:version/deprecate", () =>
		HttpResponse.json({ data: mockVersionStateDto }),
	),
	http.post("/api/v1/strategies/:id/versions/:version/reactivate", () =>
		HttpResponse.json({ data: mockActivePointerDto }),
	),

	http.get("/api/v1/research/node-descriptors", () => HttpResponse.json({ data: mockNodeDescriptorList })),
];
