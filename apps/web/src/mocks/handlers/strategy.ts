import { HttpResponse, http, type RequestHandler } from "msw";
import {
	mockActivePointerDto,
	mockNodeDescriptorList,
	mockSpecDiffDto,
	mockSpecValidationDto,
	mockStrategyDetailDto,
	mockStrategyList,
	mockStrategyVersionDetail,
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
	http.post("/api/v1/strategies", async ({ request }) => {
		const body = (await request.json()) as {
			readonly strategy_id: string;
			readonly name: string;
			readonly spec_json: Record<string, unknown>;
			readonly tags?: string[];
		};
		return HttpResponse.json({
			data: {
				strategy_id: body.strategy_id,
				name: body.name,
				spec_json: body.spec_json,
				version: 1,
				status: "draft",
				created_at: "2026-08-29T00:00:00Z",
				tags: body.tags ?? [],
			},
		});
	}),
	http.get("/api/v1/strategies/:id", ({ params }) => {
		const id = String(params["id"]);
		const found = mockStrategyList.find((s) => s.strategy_id === id) ?? mockStrategyDetailDto;
		return HttpResponse.json({ data: found });
	}),
	http.get("/api/v1/strategies/:id/versions", () => HttpResponse.json({ data: mockStrategyVersionList })),
	http.get("/api/v1/strategies/:id/versions/:version", ({ params }) =>
		HttpResponse.json({ data: { ...mockStrategyVersionDetail, version: Number(params["version"]) } }),
	),
	http.get("/api/v1/strategies/:id/active", () => HttpResponse.json({ data: mockActivePointerDto })),
	http.get("/api/v1/strategies/:id/events", ({ params, request }) => {
		const afterEventId = new URL(request.url).searchParams.get("after_event_id");
		if (afterEventId) return HttpResponse.json({ data: [] });
		return HttpResponse.json({
			data: [
				{
					event_id: "strategy-event-2",
					strategy_id: String(params["id"]),
					target_version: 3,
					event_type: "strategy.activated",
					decision_or_activation_kind: "publish",
					actor: "publisher",
					reason: "review packet accepted",
					occurred_at: "2026-07-30T02:00:00Z",
				},
				{
					event_id: "strategy-event-1",
					strategy_id: String(params["id"]),
					target_version: 3,
					event_type: "strategy.review_decided",
					decision_or_activation_kind: "approve",
					actor: "reviewer",
					reason: "hard gates clear",
					occurred_at: "2026-07-30T01:00:00Z",
				},
			],
		});
	}),
	http.get("/api/v1/strategies/:id/versions/:version/diff", () => HttpResponse.json({ data: mockSpecDiffDto })),
	http.post("/api/v1/strategies/:id/versions/:version/validate", () =>
		HttpResponse.json({ data: mockSpecValidationDto }),
	),
	http.post("/api/v1/strategies/:id/versions/:version/author-preview", async ({ params, request }) => {
		const body = (await request.json()) as {
			readonly expressions?: readonly { readonly derived_id: string; readonly version: number }[];
		};
		const operation = (kind: "draft" | "compile" | "validate" | "diff", subjectId: string, version: string) => ({
			kind,
			subject_id: subjectId,
			subject_version: version,
			valid: true,
			changed: kind === "diff",
			publishable: false as const,
			payload_hash: `mock-${kind}-${subjectId}`,
			payload: { operation: kind, publishable: false },
			lineage: [`author-preview:${kind}:${subjectId}`],
		});
		const strategyId = String(params["id"]);
		const version = String(params["version"]);
		return HttpResponse.json({
			data: {
				strategy_id: strategyId,
				base_version: Number(version),
				valid: true,
				publishable: false as const,
				canonical_hash: "h-author-candidate",
				draft: operation("draft", strategyId, "draft"),
				compile: (body.expressions ?? []).map((expression) =>
					operation("compile", expression.derived_id, String(expression.version)),
				),
				validation: operation("validate", strategyId, version),
				diff: operation("diff", strategyId, version),
				tests: [
					{ name: "canonical_hash_consistent", passed: true, detail: "one detached candidate" },
					{ name: "preview_non_publishable", passed: true, detail: "no mutation authority" },
				],
			},
		});
	}),

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
	http.post("/api/v1/strategies/:id/versions/:version/publish", () =>
		HttpResponse.json({ data: mockActivePointerDto }),
	),

	http.get("/api/v1/research/node-descriptors", () => HttpResponse.json({ data: mockNodeDescriptorList })),
];
