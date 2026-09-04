import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import {
	mockExperimentArtifacts,
	mockExperimentComparison,
	mockExperimentDetail,
	mockExperimentGates,
	mockExperimentSelectionEvidence,
} from "@/mocks/fixtures/experiment-workbench";
import { server } from "@/mocks/server";
import { ExperimentDetailPage } from "./experiment-detail-page";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

function useWorkbenchHandlers(): void {
	server.use(
		http.get("/api/v1/research/experiments/:id", () => HttpResponse.json({ data: mockExperimentDetail })),
		http.get("/api/v1/research/experiments/:id/candidates", () =>
			HttpResponse.json({ data: mockExperimentDetail.candidates }),
		),
		http.get("/api/v1/research/experiments/:id/gates", () => HttpResponse.json({ data: mockExperimentGates })),
		http.get("/api/v1/research/experiments/:id/comparison", () =>
			HttpResponse.json({ data: mockExperimentComparison }),
		),
		http.get("/api/v1/research/experiments/:id/artifacts", () => HttpResponse.json({ data: mockExperimentArtifacts })),
		http.get("/api/v1/research/experiments/:id/selection-evidence", () =>
			HttpResponse.json({ data: mockExperimentSelectionEvidence }),
		),
	);
}

describe("ExperimentDetailPage", () => {
	it("renders the exact experiment revision in a governed object hub", async () => {
		const user = userEvent.setup();
		useWorkbenchHandlers();
		render(<ExperimentDetailPage experimentId="exp-1042" />, { wrapper });

		await screen.findByText("completed · finalized · revision 9");
		const workspace = screen.getByRole("region", { name: "实验运行工作台" });
		expect(document.querySelector("[data-slot='meta']")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='tabs']")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='main']")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='bottom']")).toBeInTheDocument();
		expect(within(workspace).getByText("completed · finalized · revision 9")).toBeInTheDocument();
		expect(within(workspace).getByText("seed_stock_selection@1")).toBeInTheDocument();
		expect(screen.getByRole("tablist", { name: "实验工作台视图" })).toBeInTheDocument();

		await user.click(screen.getByRole("tab", { name: "验证与门禁" }));
		expect(screen.getByText("history_96_months")).toBeInTheDocument();
		await user.click(screen.getByRole("tab", { name: "产物与证据" }));
		expect(screen.getByText("candidate-bundle-2")).toBeInTheDocument();
		await user.click(screen.getByRole("tab", { name: "候选与选择" }));
		await user.click(screen.getAllByRole("button", { name: "查看证据" })[0]!);
		expect(screen.getByRole("tab", { name: "候选证据 · candidate-1" })).toHaveAttribute("aria-selected", "true");
		expect(screen.getByText("Candidate evidence · candidate-1")).toBeInTheDocument();
	});

	it("keeps a typed detail failure recoverable without inventing workbench data", async () => {
		const user = userEvent.setup();
		let calls = 0;
		server.use(
			http.get("/api/v1/research/experiments/:id", () => {
				calls += 1;
				return calls === 1
					? HttpResponse.json(
							{ detail: "experiment detail unavailable", error_code: "EXPERIMENT_DETAIL_UNAVAILABLE" },
							{ status: 503 },
						)
					: HttpResponse.json({ data: mockExperimentDetail });
			}),
		);
		render(<ExperimentDetailPage experimentId="exp-1042" />, { wrapper });

		expect(await screen.findByText(/503 EXPERIMENT_DETAIL_UNAVAILABLE/)).toBeInTheDocument();
		expect(screen.queryByText("seed_stock_selection@1")).not.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "重试实验详情" }));
		expect(await screen.findByRole("tablist", { name: "实验工作台视图" })).toBeInTheDocument();
		expect(calls).toBe(2);
	});

	it("fans out durable detail, candidates, gates, comparison, artifacts and stock exposure", async () => {
		const user = userEvent.setup();
		useWorkbenchHandlers();
		render(<ExperimentDetailPage experimentId="exp-1042" />, { wrapper });

		await user.click(await screen.findByRole("tab", { name: "验证与门禁" }));
		expect(screen.getByText("history_96_months")).toBeInTheDocument();
		expect(screen.getByText("partial fold failure")).toBeInTheDocument();
		await user.click(screen.getByRole("tab", { name: "产物与证据" }));
		expect(screen.getByText("candidate-bundle-2")).toBeInTheDocument();
		await expect(screen.findByText(/technology/)).resolves.toBeInTheDocument();
		expect(screen.getByText(/size_bucket_weights/)).toBeInTheDocument();
	});

	it("keeps partial resource failures visible and caps local comparison pins at four", async () => {
		const user = userEvent.setup();
		useWorkbenchHandlers();
		server.use(
			http.get("/api/v1/research/experiments/:id/comparison", () =>
				HttpResponse.json({ detail: "comparison unavailable", error_code: "COMPARISON_UNAVAILABLE" }, { status: 503 }),
			),
		);
		render(<ExperimentDetailPage experimentId="exp-1042" />, { wrapper });

		await expect(screen.findByText(/COMPARISON_UNAVAILABLE/)).resolves.toBeInTheDocument();
		for (let index = 1; index <= 4; index += 1) await user.click(screen.getByLabelText(`Pin candidate-${index}`));
		expect(screen.getByLabelText("Pin candidate-5")).toBeDisabled();
		await user.click(screen.getByRole("tab", { name: "产物与证据" }));
		expect(screen.getByText("candidate-bundle-2")).toBeInTheDocument();
	});

	it("keeps candidate promotion locked while aggregate selection evidence is unpublished", async () => {
		const user = userEvent.setup();
		useWorkbenchHandlers();
		server.use(
			http.get("/api/v1/research/experiments/:id", () =>
				HttpResponse.json({ data: { ...mockExperimentDetail, status: "running", stage: "candidate_selection" } }),
			),
			http.get("/api/v1/research/experiments/:id/selection-evidence", () =>
				HttpResponse.json(
					{ detail: "selection evidence is publishing", error_code: "SELECTION_EVIDENCE_NOT_FOUND" },
					{ status: 404 },
				),
			),
		);
		render(<ExperimentDetailPage experimentId="exp-1042" />, { wrapper });

		await expect(
			screen.findByText("Selection evidence is publishing; candidate promotion remains locked."),
		).resolves.toBeInTheDocument();
		await user.click(screen.getByLabelText("Pin candidate-2"));
		await user.type(screen.getByLabelText("晋级理由"), "wait for the immutable selection ledger");

		expect(screen.getByRole("button", { name: "选择为晋级候选 candidate-2" })).toBeDisabled();
	});

	it("does not request selection evidence before the candidate-selection gate", async () => {
		let selectionRequests = 0;
		useWorkbenchHandlers();
		server.use(
			http.get("/api/v1/research/experiments/:id", () =>
				HttpResponse.json({ data: { ...mockExperimentDetail, stage: "walk_forward" } }),
			),
			http.get("/api/v1/research/experiments/:id/selection-evidence", () => {
				selectionRequests += 1;
				return HttpResponse.json({ detail: "not published" }, { status: 404 });
			}),
		);
		render(<ExperimentDetailPage experimentId="exp-1042" />, { wrapper });

		await expect(screen.findByText(/walk_forward/)).resolves.toBeInTheDocument();
		expect(selectionRequests).toBe(0);
	});
});
