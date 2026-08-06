import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { mockExperimentDetail } from "@/mocks/fixtures/experiment-workbench";
import { server } from "@/mocks/server";
import {
	comparisonEvidencePollingInterval,
	experimentPollingInterval,
	selectionEvidencePollingInterval,
	useExperiment,
} from "../hooks/use-experiment";
import { ExperimentRunControls } from "./experiment-run-controls";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

function wrapperWith(client: QueryClient) {
	return function QueryWrapper({ children }: { readonly children: ReactNode }) {
		return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
	};
}

describe("ExperimentRunControls recovery", () => {
	it("polls only from active server statuses", () => {
		expect(experimentPollingInterval("queued")).toBe(2000);
		expect(experimentPollingInterval("running")).toBe(2000);
		expect(experimentPollingInterval("pausing")).toBe(2000);
		expect(experimentPollingInterval("pause_requested")).toBe(2000);
		expect(experimentPollingInterval("cancel_requested")).toBe(2000);
		expect(experimentPollingInterval("paused")).toBe(false);
		expect(experimentPollingInterval("completed")).toBe(false);
		expect(experimentPollingInterval(undefined)).toBe(false);
	});

	it("polls for selection evidence only while an evidence-bearing stage is still publishing it", () => {
		expect(selectionEvidencePollingInterval("walk_forward", false)).toBe(false);
		expect(selectionEvidencePollingInterval("candidate_selection", false)).toBe(2000);
		expect(selectionEvidencePollingInterval("holdout", false)).toBe(2000);
		expect(selectionEvidencePollingInterval("evidence", false)).toBe(2000);
		expect(selectionEvidencePollingInterval("finalized", false)).toBe(2000);
		expect(selectionEvidencePollingInterval("candidate_selection", true)).toBe(false);
	});

	it("keeps polling comparison evidence until it matches the latest server revision", () => {
		expect(comparisonEvidencePollingInterval("candidate_selection", 8, 12)).toBe(2000);
		expect(comparisonEvidencePollingInterval("candidate_selection", undefined, 12)).toBe(2000);
		expect(comparisonEvidencePollingInterval("candidate_selection", 12, 12)).toBe(false);
		expect(comparisonEvidencePollingInterval("walk_forward", 8, 12)).toBe(false);
	});

	it("reconstructs status from server truth after remount", async () => {
		let status = "running";
		let revision = 9;
		server.use(
			http.get("/api/v1/research/experiments/:id", () =>
				HttpResponse.json({ data: { ...mockExperimentDetail, status, revision } }),
			),
		);

		const firstClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
		const first = renderHook(() => useExperiment("exp-1042"), { wrapper: wrapperWith(firstClient) });
		await waitFor(() => expect(first.result.current.data?.status).toBe("running"));
		first.unmount();
		firstClient.clear();

		status = "paused";
		revision = 10;
		const secondClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
		const second = renderHook(() => useExperiment("exp-1042"), { wrapper: wrapperWith(secondClient) });
		await waitFor(() => expect(second.result.current.data).toMatchObject({ status: "paused", revision: 10 }));
		second.unmount();
		secondClient.clear();
	});

	it("sends latest server revision with an idempotency key and refreshes receipt truth", async () => {
		const user = userEvent.setup();
		let expectedRevision = -1;
		let key = "";
		server.use(
			http.post("/api/v1/research/experiments/:id/pause", async ({ request }) => {
				expectedRevision = ((await request.json()) as { expected_revision: number }).expected_revision;
				key = request.headers.get("Idempotency-Key") ?? "";
				return HttpResponse.json({
					data: {
						experiment_id: "exp-1042",
						status: "pausing",
						desired_state: "paused",
						revision: 10,
						live_run_ids: ["run-1"],
						occurred_at: "2026-08-01T00:00:00Z",
					},
				});
			}),
		);

		render(
			<ExperimentRunControls detail={{ ...mockExperimentDetail, status: "running", desired_state: "running" }} />,
			{ wrapper },
		);
		await user.click(screen.getByRole("button", { name: "暂停" }));
		await expect(screen.findByText(/pausing/)).resolves.toBeInTheDocument();
		expect(expectedRevision).toBe(9);
		expect(key).toBeTruthy();
	});

	it("shows network failure and never advances a synthetic progress value", async () => {
		server.use(http.post("/api/v1/research/experiments/:id/pause", () => HttpResponse.error()));
		const user = userEvent.setup();
		render(
			<ExperimentRunControls detail={{ ...mockExperimentDetail, status: "running", desired_state: "running" }} />,
			{ wrapper },
		);
		await user.click(screen.getByRole("button", { name: "暂停" }));
		await expect(screen.findByRole("alert")).resolves.toBeInTheDocument();
		expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
	});

	it("reuses the exact control key when a 503 leaves the result unknown", async () => {
		const user = userEvent.setup();
		const keys: string[] = [];
		let calls = 0;
		server.use(
			http.post("/api/v1/research/experiments/:id/pause", ({ request }) => {
				calls += 1;
				keys.push(request.headers.get("Idempotency-Key") ?? "");
				if (calls === 1)
					return HttpResponse.json({ detail: "unknown", error_code: "CONTROL_OUTCOME_UNKNOWN" }, { status: 503 });
				return HttpResponse.json({
					data: {
						experiment_id: "exp-1042",
						status: "pausing",
						desired_state: "paused",
						revision: 10,
						live_run_ids: [],
						occurred_at: "2026-08-01T00:00:00Z",
					},
				});
			}),
		);
		render(
			<ExperimentRunControls detail={{ ...mockExperimentDetail, status: "running", desired_state: "running" }} />,
			{ wrapper },
		);
		await user.click(screen.getByRole("button", { name: "暂停" }));
		await expect(screen.findByText(/CONTROL_OUTCOME_UNKNOWN/)).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "暂停" }));
		await expect.poll(() => calls).toBe(2);
		expect(keys[0]).toBeTruthy();
		expect(keys[1]).toBe(keys[0]);
	});
});
