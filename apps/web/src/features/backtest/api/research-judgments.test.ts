import { afterEach, describe, expect, it, vi } from "vitest";
import { capturedRequest, requestJson, requestPath } from "@/test/request";
import { fetchResearchJudgment, listResearchJudgments, recordResearchJudgment } from "./research-judgments";

const JUDGMENT_ID = `research-judgment:sha256:${"a".repeat(64)}`;

function jsonResponse(value: unknown, status = 200): Response {
	return new Response(JSON.stringify(value), {
		status,
		headers: { "content-type": "application/json" },
	});
}

afterEach(() => vi.unstubAllGlobals());

describe("research judgment api client", () => {
	it("records a judgment with strategy fields and validates the returned identity", async () => {
		const fetchMock = vi.fn<typeof fetch>(async () =>
			jsonResponse(
				{
					judgment_id: JUDGMENT_ID,
					run_ids: ["run-a", "run-b"],
					judgment: "结论",
					created_at: "2026-11-12T06:00:00+00:00",
					strategy_id: "s1",
					strategy_version: 2,
				},
				201,
			),
		);
		vi.stubGlobal("fetch", fetchMock);

		const saved = await recordResearchJudgment({
			runIds: ["run-a", "run-b"],
			judgment: "结论",
			strategyId: "s1",
			strategyVersion: 2,
		});
		expect(saved).toEqual({
			judgmentId: JUDGMENT_ID,
			runIds: ["run-a", "run-b"],
			judgment: "结论",
			createdAt: "2026-11-12T06:00:00+00:00",
			strategyId: "s1",
			strategyVersion: 2,
		});
		const body = (await requestJson(capturedRequest(fetchMock.mock.calls))) as Record<string, unknown>;
		expect(body["strategy_id"]).toBe("s1");
		expect(body["strategy_version"]).toBe(2);
	});

	it("omits strategy fields when unspecified and normalizes null strategy in summaries", async () => {
		const fetchMock = vi.fn<typeof fetch>(async (input: RequestInfo | URL) => {
			const url = new URL(input instanceof Request ? input.url : String(input));
			if (url.pathname === "/api/v1/research/judgments" && url.search === "") {
				return jsonResponse(
					{
						judgment_id: JUDGMENT_ID,
						run_ids: ["run-a"],
						judgment: "j",
						created_at: "t",
						strategy_id: null,
						strategy_version: null,
					},
					201,
				);
			}
			return jsonResponse([
				{
					judgment_id: JUDGMENT_ID,
					run_ids: ["run-a"],
					created_at: "t",
					judgment: "j",
					strategy_id: null,
					strategy_version: null,
				},
			]);
		});
		vi.stubGlobal("fetch", fetchMock);

		const withoutStrategy = await recordResearchJudgment({ runIds: ["run-a"], judgment: "j" });
		expect(withoutStrategy.strategyId).toBeNull();
		expect(withoutStrategy.strategyVersion).toBeNull();
		const body = (await requestJson(capturedRequest(fetchMock.mock.calls))) as Record<string, unknown>;
		expect("strategy_id" in body).toBe(false);

		const listed = await listResearchJudgments();
		expect(listed[0]?.strategyId).toBeNull();
		expect(listed[0]?.strategyVersion).toBeNull();
		expect(requestPath(capturedRequest(fetchMock.mock.calls, 1))).toBe("/api/v1/research/judgments?limit=20");
	});

	it("fetches one judgment and rejects a mismatched identity", async () => {
		const fetchMock = vi.fn(async () =>
			jsonResponse({
				judgment_id: `research-judgment:sha256:${"b".repeat(64)}`,
				run_ids: ["run-a"],
				judgment: "j",
				created_at: "t",
				strategy_id: null,
				strategy_version: null,
			}),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(fetchResearchJudgment(JUDGMENT_ID)).rejects.toThrow("研究判断响应身份不匹配");
	});

	it("rejects a record response without a content-addressed identity", async () => {
		const fetchMock = vi.fn(async () =>
			jsonResponse(
				{
					judgment_id: "not-a-judgment",
					run_ids: ["run-a"],
					judgment: "j",
					created_at: "t",
					strategy_id: null,
					strategy_version: null,
				},
				201,
			),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(recordResearchJudgment({ runIds: ["run-a"], judgment: "j" })).rejects.toThrow("研究判断响应身份无效");
	});
});
