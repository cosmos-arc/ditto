import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import type { FactorDiagnosticsScope } from "../api/factor-diagnostics";
import { FactorDiagnosticsView } from "./factor-diagnostics-view";

const SCOPE: FactorDiagnosticsScope = {
	snapshotId: "snapshot-r3",
	startDate: "2024-01-01",
	endDate: "2024-12-31",
	registryHash: "f".repeat(64),
};

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

describe("FactorDiagnosticsView", () => {
	it("requests one exact full scope and renders immutable provenance", async () => {
		let query = new URLSearchParams();
		server.use(
			http.get("/api/v1/research/factors/:factorId/diagnostics", ({ request }) => {
				query = new URL(request.url).searchParams;
				return HttpResponse.json({
					data: {
						factor_id: "momentum_1m",
						snapshot_id: SCOPE.snapshotId,
						snapshot_hash: "a".repeat(64),
						registry_hash: SCOPE.registryHash,
						start_date: SCOPE.startDate,
						end_date: SCOPE.endDate,
						provenance: { dataset_id: "stock_daily", universe: "a-share-r3" },
						metrics: { coverage: 0.97, rank_ic: 0.08 },
						artifact_id: "factor-diagnostic-1",
						content_hash: "c".repeat(64),
					},
				});
			}),
		);

		render(<FactorDiagnosticsView factorId="momentum_1m" scope={SCOPE} />, { wrapper });

		await expect(screen.findByText("factor-diagnostic-1")).resolves.toBeInTheDocument();
		expect(screen.getByText(SCOPE.snapshotId)).toBeInTheDocument();
		expect(screen.getByText(SCOPE.registryHash)).toBeInTheDocument();
		expect(screen.getByText("2024-01-01 → 2024-12-31")).toBeInTheDocument();
		expect(screen.getByText("c".repeat(64))).toBeInTheDocument();
		expect(query.get("snapshot_id")).toBe(SCOPE.snapshotId);
		expect(query.get("registry_hash")).toBe(SCOPE.registryHash);
	});

	it("renders typed failure and retries without prototype fallback", async () => {
		let calls = 0;
		server.use(
			http.get("/api/v1/research/factors/:factorId/diagnostics", () => {
				calls += 1;
				if (calls === 1) {
					return HttpResponse.json(
						{ detail: "artifact unavailable", error_code: "DIAGNOSTIC_NOT_FOUND" },
						{ status: 404 },
					);
				}
				return HttpResponse.json({
					data: {
						factor_id: "momentum_1m",
						snapshot_id: SCOPE.snapshotId,
						snapshot_hash: "a".repeat(64),
						registry_hash: SCOPE.registryHash,
						start_date: SCOPE.startDate,
						end_date: SCOPE.endDate,
						provenance: {},
						metrics: {},
						artifact_id: "factor-diagnostic-retry",
						content_hash: "d".repeat(64),
					},
				});
			}),
		);

		const user = userEvent.setup();
		render(<FactorDiagnosticsView factorId="momentum_1m" scope={SCOPE} />, { wrapper });
		await expect(screen.findByText(/DIAGNOSTIC_NOT_FOUND/)).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "重试诊断" }));
		await expect(screen.findByText("factor-diagnostic-retry")).resolves.toBeInTheDocument();
		expect(calls).toBe(2);
	});
});
