import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { mockExperimentComparison, mockExperimentDetail } from "@/mocks/fixtures/experiment-workbench";
import { server } from "@/mocks/server";
import { CandidateComparison } from "./candidate-comparison";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

describe("candidate selection and holdout", () => {
	it("keeps candidate selection disabled until aggregate selection evidence is ready", async () => {
		const user = userEvent.setup();
		render(
			<CandidateComparison
				experimentId="exp-1042"
				revision={9}
				candidates={mockExperimentDetail.candidates}
				comparison={mockExperimentComparison}
				selectionEvidenceReady={false}
				selectionState={null}
			/>,
			{ wrapper },
		);

		await user.click(screen.getByLabelText("Pin candidate-2"));
		await user.type(screen.getByLabelText("晋级理由"), "wait for the immutable selection ledger");

		expect(screen.getByRole("button", { name: "选择为晋级候选 candidate-2" })).toBeDisabled();
	});

	it("never offers the registered baseline as a promotable candidate", async () => {
		const user = userEvent.setup();
		render(
			<CandidateComparison
				experimentId="exp-1042"
				revision={9}
				candidates={mockExperimentDetail.candidates}
				comparison={mockExperimentComparison}
				selectionEvidenceReady={true}
				selectionState={null}
			/>,
			{ wrapper },
		);

		await user.click(screen.getByLabelText("Pin candidate-1"));
		await user.type(screen.getByLabelText("晋级理由"), "baseline cannot be promoted");

		expect(screen.getByRole("button", { name: "选择为晋级候选 candidate-1" })).toBeDisabled();
	});

	it("persists only an explicit selection then enables holdout for the returned selection_id", async () => {
		const user = userEvent.setup();
		let selectionBody: Record<string, unknown> = {};
		let selectionKey = "";
		let holdoutBody: Record<string, unknown> = {};
		server.use(
			http.post("/api/v1/research/experiments/:id/candidate-selection", async ({ request }) => {
				selectionBody = (await request.json()) as Record<string, unknown>;
				selectionKey = request.headers.get("Idempotency-Key") ?? "";
				return HttpResponse.json({
					data: {
						selection_id: "selection-1",
						experiment_id: "exp-1042",
						candidate_id: "candidate-2",
						comparison_payload_hash: "e".repeat(64),
						candidate_evidence_artifact_id: "candidate-bundle-2",
						candidate_evidence_content_hash: "2".repeat(64),
						selection_evidence_content_hash: "5".repeat(64),
						revision: 10,
						event_id: "event-selection-1",
						occurred_at: "2026-08-01T00:00:00Z",
					},
				});
			}),
			http.post("/api/v1/research/experiments/:id/holdout-evaluations", async ({ request }) => {
				holdoutBody = (await request.json()) as Record<string, unknown>;
				return HttpResponse.json({
					data: {
						selection_id: "selection-1",
						claim_id: "claim-1",
						experiment_id: "exp-1042",
						candidate_id: "candidate-2",
						fold_id: "holdout",
						logical_run_id: "run-holdout",
						reproduction_fingerprint: "9".repeat(64),
						expected: true,
						candidate_evidence_content_hash: "2".repeat(64),
						selection_evidence_content_hash: "5".repeat(64),
						claim_payload_hash: "8".repeat(64),
						revision: 11,
						event_id: "event-holdout-1",
						occurred_at: "2026-08-01T00:01:00Z",
						state: "claimed",
					},
				});
			}),
		);

		render(
			<CandidateComparison
				experimentId="exp-1042"
				revision={9}
				candidates={mockExperimentDetail.candidates}
				comparison={mockExperimentComparison}
				selectionEvidenceReady={true}
				selectionState={null}
			/>,
			{ wrapper },
		);
		await user.click(screen.getByLabelText("Pin candidate-2"));
		expect(selectionBody).toEqual({});
		await user.type(screen.getByLabelText("晋级理由"), "registered objective winner");
		await user.click(screen.getByRole("button", { name: "选择为晋级候选 candidate-2" }));
		await expect(screen.findByText(/selection-1/)).resolves.toBeInTheDocument();
		expect(selectionBody).toMatchObject({
			candidate_id: "candidate-2",
			comparison_payload_hash: "e".repeat(64),
			expected_revision: 9,
		});
		expect(selectionKey).toBeTruthy();

		await user.click(screen.getByRole("button", { name: "执行一次性 Holdout" }));
		await expect(screen.findByText(/claim-1/)).resolves.toBeInTheDocument();
		expect(holdoutBody).toMatchObject({
			selection_id: "selection-1",
			candidate_id: "candidate-2",
			expected_revision: 10,
		});
	});

	it("enables holdout from the server receipt without waiting for cache refreshes", async () => {
		const user = userEvent.setup();
		const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
		vi.spyOn(queryClient, "invalidateQueries").mockReturnValue(new Promise(() => {}));
		server.use(
			http.post("/api/v1/research/experiments/:id/candidate-selection", () =>
				HttpResponse.json({
					data: {
						selection_id: "selection-refresh-pending",
						experiment_id: "exp-1042",
						candidate_id: "candidate-2",
						comparison_payload_hash: "e".repeat(64),
						candidate_evidence_artifact_id: "candidate-bundle-2",
						candidate_evidence_content_hash: "2".repeat(64),
						selection_evidence_content_hash: "5".repeat(64),
						revision: 10,
						event_id: "event-selection-refresh-pending",
						occurred_at: "2026-08-01T00:00:00Z",
					},
				}),
			),
			http.post("/api/v1/research/experiments/:id/holdout-evaluations", () =>
				HttpResponse.json({
					data: {
						selection_id: "selection-refresh-pending",
						claim_id: "claim-refresh-pending",
						experiment_id: "exp-1042",
						candidate_id: "candidate-2",
						fold_id: "holdout",
						logical_run_id: "run-holdout",
						reproduction_fingerprint: "9".repeat(64),
						expected: true,
						candidate_evidence_content_hash: "2".repeat(64),
						selection_evidence_content_hash: "5".repeat(64),
						claim_payload_hash: "8".repeat(64),
						revision: 11,
						event_id: "event-holdout-refresh-pending",
						occurred_at: "2026-08-01T00:01:00Z",
						state: "claimed",
					},
				}),
			),
		);

		render(
			<QueryClientProvider client={queryClient}>
				<CandidateComparison
					experimentId="exp-1042"
					revision={9}
					candidates={mockExperimentDetail.candidates}
					comparison={mockExperimentComparison}
					selectionEvidenceReady={true}
					selectionState={null}
				/>
			</QueryClientProvider>,
		);
		await user.click(screen.getByLabelText("Pin candidate-2"));
		await user.type(screen.getByLabelText("晋级理由"), "server receipt is authoritative");
		await user.click(screen.getByRole("button", { name: "选择为晋级候选 candidate-2" }));

		await expect(
			screen.findByRole("button", { name: "执行一次性 Holdout" }, { timeout: 1_000 }),
		).resolves.toBeEnabled();
		await user.click(screen.getByRole("button", { name: "执行一次性 Holdout" }));
		await expect(screen.findByText(/claim-refresh-pending/, {}, { timeout: 1_000 })).resolves.toBeInTheDocument();
	});

	it("recovers persisted selection and holdout consumption after remount", () => {
		render(
			<CandidateComparison
				experimentId="exp-1042"
				revision={11}
				candidates={mockExperimentDetail.candidates}
				comparison={mockExperimentComparison}
				selectionEvidenceReady={true}
				selectionState={{
					selection_id: "selection-from-server-truth",
					experiment_id: "exp-1042",
					candidate_id: "candidate-2",
					comparison_payload_hash: "e".repeat(64),
					candidate_evidence_artifact_id: "candidate-bundle-2",
					candidate_evidence_content_hash: "2".repeat(64),
					selection_evidence_content_hash: "5".repeat(64),
					revision: 10,
					event_id: "event-selection-server-truth",
					occurred_at: "2026-08-01T00:00:00Z",
					holdout_claim_id: "claim-from-server-truth",
				}}
			/>,
			{ wrapper },
		);

		expect(screen.getByText(/selection-from-server-truth/)).toBeInTheDocument();
		expect(screen.getByText(/claim-from-server-truth/)).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "执行一次性 Holdout" })).toBeDisabled();
	});

	it("fails closed on a duplicate holdout claim", async () => {
		const user = userEvent.setup();
		server.use(
			http.post("/api/v1/research/experiments/:id/candidate-selection", () =>
				HttpResponse.json({
					data: {
						selection_id: "selection-1",
						experiment_id: "exp-1042",
						candidate_id: "candidate-2",
						comparison_payload_hash: "e".repeat(64),
						candidate_evidence_artifact_id: "candidate-bundle-2",
						candidate_evidence_content_hash: "2".repeat(64),
						selection_evidence_content_hash: "5".repeat(64),
						revision: 10,
						event_id: "event-selection-1",
						occurred_at: "2026-08-01T00:00:00Z",
					},
				}),
			),
			http.post("/api/v1/research/experiments/:id/holdout-evaluations", () =>
				HttpResponse.json({ detail: "already claimed", error_code: "HOLDOUT_ALREADY_CLAIMED" }, { status: 409 }),
			),
		);
		render(
			<CandidateComparison
				experimentId="exp-1042"
				revision={9}
				candidates={mockExperimentDetail.candidates}
				comparison={mockExperimentComparison}
				selectionEvidenceReady={true}
				selectionState={null}
			/>,
			{ wrapper },
		);
		await user.click(screen.getByLabelText("Pin candidate-2"));
		await user.type(screen.getByLabelText("晋级理由"), "winner");
		await user.click(screen.getByRole("button", { name: "选择为晋级候选 candidate-2" }));
		await user.click(await screen.findByRole("button", { name: "执行一次性 Holdout" }));
		await expect(screen.findByText(/HOLDOUT_ALREADY_CLAIMED/)).resolves.toBeInTheDocument();
		expect(screen.getByRole("button", { name: "执行一次性 Holdout" })).toBeDisabled();
	});
});
