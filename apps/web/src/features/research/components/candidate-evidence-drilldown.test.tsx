import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { fetchCandidateEvidencePage } from "../api/candidate-evidence";
import { CandidateEvidenceDrilldown } from "./candidate-evidence-drilldown";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

describe("CandidateEvidenceDrilldown", () => {
	it("rejects a cursor copied from another resource kind before any request", async () => {
		await expect(
			fetchCandidateEvidencePage("exp-1042", "candidate-2", "selections", {
				cursor: "cross-kind",
				experimentId: "exp-1042",
				candidateId: "candidate-2",
				candidateBundleArtifactId: "bundle-2",
				contentHash: "2".repeat(64),
				resourceKind: "exclusions",
			}),
		).rejects.toThrow("INVALID_CANDIDATE_EVIDENCE_CURSOR");
	});
	it("loads all three scoped resources and follows only each server next_cursor", async () => {
		const user = userEvent.setup();
		const cursors: Array<string | null> = [];
		server.use(
			http.get("/api/v1/research/candidates/:candidateId/selections", ({ request }) => {
				const cursor = new URL(request.url).searchParams.get("cursor");
				cursors.push(cursor);
				return HttpResponse.json({
					data: {
						candidate_id: "candidate-2",
						experiment_id: "exp-1042",
						artifact_id: "bundle-2",
						content_hash: "2".repeat(64),
						items: [
							{
								fold_id: cursor ? "fold-2" : "fold-1",
								validation_fold_ordinal: cursor ? 2 : 1,
								trade_date: cursor ? "2022-01-03" : "2021-01-04",
								instrument_id: cursor ? "000002" : "000001",
								rank: 1,
								score: 0.9,
								selected: true,
								evidence_hash: cursor ? "b".repeat(64) : "a".repeat(64),
							},
						],
						next_cursor: cursor ? null : "server-cursor-2",
					},
				});
			}),
			http.get("/api/v1/research/candidates/:candidateId/exclusions", () =>
				HttpResponse.json({
					data: {
						candidate_id: "candidate-2",
						experiment_id: "exp-1042",
						artifact_id: "bundle-2",
						content_hash: "2".repeat(64),
						items: [],
						next_cursor: null,
					},
				}),
			),
			http.get("/api/v1/research/candidates/:candidateId/factor-contributions", () =>
				HttpResponse.json({
					data: {
						candidate_id: "candidate-2",
						experiment_id: "exp-1042",
						artifact_id: "bundle-2",
						content_hash: "2".repeat(64),
						items: [
							{
								fold_id: "fold-1",
								validation_fold_ordinal: 1,
								trade_date: "2021-01-04",
								instrument_id: "000001",
								factor_id: "momentum",
								rank: 1,
								selected: true,
								contribution: 0.12,
								evidence_hash: "c".repeat(64),
							},
						],
						next_cursor: null,
					},
				}),
			),
		);

		render(<CandidateEvidenceDrilldown experimentId="exp-1042" candidateId="candidate-2" />, { wrapper });
		await expect(screen.findByText(/momentum/)).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "加载更多 selections" }));
		const selections = screen.getByRole("heading", { name: "selections" }).closest("section");
		expect(selections).not.toBeNull();
		const secondFold = await within(selections as HTMLElement).findByText(/000002/);
		const firstFold = within(selections as HTMLElement).getByText(/000001/);
		expect(cursors).toEqual([null, "server-cursor-2"]);
		expect(within(selections as HTMLElement).getAllByText(/000001/)).toHaveLength(1);
		expect(within(selections as HTMLElement).getAllByText(/000002/)).toHaveLength(1);
		expect(firstFold.compareDocumentPosition(secondFold) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
	});

	it("rebuilds the same bundle identity and rows from server truth after remount", async () => {
		let selectionRequests = 0;
		server.use(
			http.get("/api/v1/research/candidates/:candidateId/selections", () => {
				selectionRequests += 1;
				return HttpResponse.json({
					data: {
						candidate_id: "candidate-2",
						experiment_id: "exp-1042",
						artifact_id: "bundle-parity",
						content_hash: "7".repeat(64),
						items: [
							{
								fold_id: "fold-parity",
								validation_fold_ordinal: 1,
								trade_date: "2021-01-04",
								instrument_id: "PARITY-ROW",
								rank: 1,
								score: 0.9,
								selected: true,
								evidence_hash: "a".repeat(64),
							},
						],
						next_cursor: null,
					},
				});
			}),
			http.get(/\/api\/v1\/research\/candidates\/.*\/(exclusions|factor-contributions)/, () =>
				HttpResponse.json({
					data: {
						candidate_id: "candidate-2",
						experiment_id: "exp-1042",
						artifact_id: "bundle-parity",
						content_hash: "7".repeat(64),
						items: [],
						next_cursor: null,
					},
				}),
			),
		);

		const first = render(<CandidateEvidenceDrilldown experimentId="exp-1042" candidateId="candidate-2" />, { wrapper });
		await expect(screen.findByText(/PARITY-ROW/)).resolves.toBeInTheDocument();
		expect(screen.getAllByText(/bundle-parity/)).toHaveLength(3);
		first.unmount();

		render(<CandidateEvidenceDrilldown experimentId="exp-1042" candidateId="candidate-2" />, { wrapper });
		await expect(screen.findByText(/PARITY-ROW/)).resolves.toBeInTheDocument();
		expect(screen.getAllByText(/bundle-parity/)).toHaveLength(3);
		expect(selectionRequests).toBe(2);
	});

	it("clears old visible pages and fails closed when the server reports EVIDENCE_STALE", async () => {
		const user = userEvent.setup();
		server.use(
			http.get("/api/v1/research/candidates/:candidateId/selections", ({ request }) => {
				const cursor = new URL(request.url).searchParams.get("cursor");
				if (cursor)
					return HttpResponse.json({ detail: "bundle changed", error_code: "EVIDENCE_STALE" }, { status: 409 });
				return HttpResponse.json({
					data: {
						candidate_id: "candidate-2",
						experiment_id: "exp-1042",
						artifact_id: "bundle-old",
						content_hash: "2".repeat(64),
						items: [
							{
								fold_id: "fold-old",
								validation_fold_ordinal: 1,
								trade_date: "2021-01-04",
								instrument_id: "OLD-ROW",
								rank: 1,
								score: 0.9,
								selected: true,
								evidence_hash: "a".repeat(64),
							},
						],
						next_cursor: "old-cursor",
					},
				});
			}),
			http.get(/\/api\/v1\/research\/candidates\/.*\/(exclusions|factor-contributions)/, () =>
				HttpResponse.json({
					data: {
						candidate_id: "candidate-2",
						experiment_id: "exp-1042",
						artifact_id: "bundle-old",
						content_hash: "2".repeat(64),
						items: [],
						next_cursor: null,
					},
				}),
			),
		);
		render(<CandidateEvidenceDrilldown experimentId="exp-1042" candidateId="candidate-2" />, { wrapper });
		await expect(screen.findByText(/OLD-ROW/)).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "加载更多 selections" }));
		await expect(screen.findByText(/EVIDENCE_STALE/)).resolves.toBeInTheDocument();
		expect(screen.queryByText(/OLD-ROW/)).not.toBeInTheDocument();
	});
});
