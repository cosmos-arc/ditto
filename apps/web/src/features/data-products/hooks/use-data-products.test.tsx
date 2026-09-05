import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { delay, HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import {
	useDataProductCoverage,
	useDataProductEvidence,
	useDataProductLicense,
	useDataProductQuality,
	useDataProductRuns,
	useDataProducts,
} from "./use-data-products";

function createWrapper(): ({ children }: { readonly children: ReactNode }) => ReactNode {
	const queryClient = new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
		},
	});
	return function Wrapper({ children }: { readonly children: ReactNode }): ReactNode {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

const overview = {
	dataset_id: "stock_daily",
	r2_scope: "hard",
	maturity: "certified",
	schedule: "trading_day",
	owner: "data-platform",
	raw_target_from: "2005-01-01",
	certified_target_from: "2015-01-01",
	active_certification_report_id: "cert-stock-daily-1",
};

beforeEach(() => {
	vi.stubEnv("VITE_USE_MOCK", "false");
});

describe("useDataProducts", () => {
	it("exposes a loading state before the real overview request resolves", async () => {
		server.use(
			http.get("/api/v1/data-products", async () => {
				await delay(50);
				return HttpResponse.json({ data: [overview] });
			}),
		);

		const { result } = renderHook(() => useDataProducts(), { wrapper: createWrapper() });

		expect(result.current.isLoading).toBe(true);
		await waitFor(() => expect(result.current.isSuccess).toBe(true));
	});

	it("preserves an empty product catalog as a successful response", async () => {
		server.use(http.get("/api/v1/data-products", () => HttpResponse.json({ data: [] })));

		const { result } = renderHook(() => useDataProducts(), { wrapper: createWrapper() });

		await waitFor(() => expect(result.current.isSuccess).toBe(true));
		expect(result.current.data).toEqual([]);
	});

	it("surfaces API errors without falling back to prototype fixtures", async () => {
		server.use(
			http.get("/api/v1/data-products", () => HttpResponse.json({ detail: "catalog unavailable" }, { status: 503 })),
		);

		const { result } = renderHook(() => useDataProducts(), { wrapper: createWrapper() });

		await waitFor(() => expect(result.current.isError).toBe(true));
		expect(result.current.error?.message).toBe("catalog unavailable");
	});

	it("loads the generated API projection from the v1 route", async () => {
		let requestedProfile: string | null = null;
		server.use(
			http.get("/api/v1/data-products", ({ request }) => {
				requestedProfile = new URL(request.url).searchParams.get("profile");
				return HttpResponse.json({ data: [overview] });
			}),
		);

		const { result } = renderHook(() => useDataProducts("strategy_daily"), { wrapper: createWrapper() });

		await waitFor(() => expect(result.current.isSuccess).toBe(true));
		expect(requestedProfile).toBe("strategy_daily");
		expect(result.current.data?.[0]?.dataset_id).toBe("stock_daily");
	});
});

describe("data product evidence hooks", () => {
	it("calls every dataset-scoped v1 endpoint with an encoded id and profile", async () => {
		const requestedPaths: string[] = [];
		server.use(
			http.get("/api/v1/data-products/:datasetId/:view", ({ params, request }) => {
				const url = new URL(request.url);
				const path = `${url.pathname.replace("/api/v1/data-products/", "")}?${url.searchParams.toString()}`;
				requestedPaths.push(path);
				if (params["view"] === "coverage") {
					return HttpResponse.json({
						data: {
							dataset_id: "index weight",
							profile: "research_daily",
							raw_from: "2005-01-01",
							complete_from: "2015-01-01",
							certified_from: "2015-01-01",
							expected_partitions: 10,
							actual_partitions: 10,
							gaps: [],
							unapproved_gaps: [],
						},
					});
				}
				if (params["view"] === "quality") {
					return HttpResponse.json({
						data: {
							dataset_id: "index weight",
							profile: "research_daily",
							report_id: "cert-1",
							dq_rule_version: "dq-v1",
							dq_results: [],
							pit_replay_results: [],
							freshness_results: [],
							recovery_results: [],
							consumer_results: [],
						},
					});
				}
				if (params["view"] === "runs") return HttpResponse.json({ data: [] });
				if (params["view"] === "evidence") {
					return HttpResponse.json({
						data: {
							dataset_id: "index weight",
							profile: "research_daily",
							report_id: "cert-1",
							content_hash: "sha256:abc",
							source_ids: ["tushare"],
							schema_versions: ["index_weight:v1"],
							snapshot_ids: ["snapshot-1"],
							fallback_history: [],
							override_history: [],
						},
					});
				}
				return HttpResponse.json({
					data: {
						dataset_id: "index weight",
						profile: "research_daily",
						report_id: "cert-1",
						license_record_ids: ["license-tushare-v1"],
					},
				});
			}),
		);

		const wrapper = createWrapper();
		const hooks = [
			renderHook(() => useDataProductCoverage("index weight"), { wrapper }),
			renderHook(() => useDataProductQuality("index weight"), { wrapper }),
			renderHook(() => useDataProductRuns("index weight"), { wrapper }),
			renderHook(() => useDataProductEvidence("index weight"), { wrapper }),
			renderHook(() => useDataProductLicense("index weight"), { wrapper }),
		];

		await waitFor(() => expect(hooks.every(({ result }) => result.current.isSuccess)).toBe(true));
		expect(requestedPaths.sort()).toEqual(
			[
				"index%20weight/coverage?profile=research_daily",
				"index%20weight/evidence?profile=research_daily",
				"index%20weight/license?profile=research_daily",
				"index%20weight/quality?profile=research_daily",
				"index%20weight/runs?profile=research_daily",
			].sort(),
		);
	});
});
