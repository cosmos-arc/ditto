import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
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
	it("fans out durable detail, candidates, gates, comparison, artifacts and stock exposure", async () => {
		useWorkbenchHandlers();
		render(<ExperimentDetailPage experimentId="exp-1042" />, { wrapper });

		await expect(screen.findByText("history_96_months")).resolves.toBeInTheDocument();
		expect(screen.getByText("candidate-bundle-2")).toBeInTheDocument();
		await expect(screen.findByText(/technology/)).resolves.toBeInTheDocument();
		expect(screen.getByText(/size_bucket_weights/)).toBeInTheDocument();
		expect(screen.getByText("partial fold failure")).toBeInTheDocument();
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
		expect(screen.getByText("candidate-bundle-2")).toBeInTheDocument();
		for (let index = 1; index <= 4; index += 1) await user.click(screen.getByLabelText(`Pin candidate-${index}`));
		expect(screen.getByLabelText("Pin candidate-5")).toBeDisabled();
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
