import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { mockReviewPacket } from "@/mocks/fixtures/review-live";
import { server } from "@/mocks/server";
import type { StrategyVersion } from "@/types/strategy";
import { StrategyReviewGovernanceActions } from ".";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

function version(experimentId: string | null = "exp-gov"): StrategyVersion {
	return {
		strategyId: "s",
		version: 2,
		parentVersion: 1,
		specHash: "a".repeat(64),
		state: "review",
		lifecycleState: "review",
		reviewOutcome: "pending",
		createdAt: "2026-01-01T00:00:00Z",
		experimentId,
	};
}

function renderActions(experimentId: string | null = "exp-gov") {
	render(
		<StrategyReviewGovernanceActions
			strategyId="s"
			version={version(experimentId)}
			expectedPointerRevision={null}
			currentActiveVersion={null}
		/>,
		{ wrapper },
	);
}

function reviewPacket(hardReviewBlocked: boolean, bundleHash = mockReviewPacket.bundle_hash) {
	server.use(
		http.get("/api/v1/research/experiments/exp-gov/review-packet", () =>
			HttpResponse.json({
				data: {
					...mockReviewPacket,
					experiment_id: "exp-gov",
					bundle_hash: bundleHash,
					hard_review_blocked: hardReviewBlocked,
				},
			}),
		),
	);
}

describe("Strategy review governance workflow", () => {
	it("enables approval only after a valid persisted packet clears hard gates", async () => {
		reviewPacket(false);
		renderActions();

		await waitFor(() => expect(screen.getByRole("button", { name: "批准" })).toBeEnabled());
		expect(screen.queryByRole("alert")).not.toBeInTheDocument();
	});

	it("fails closed and explains a hard-gate block", async () => {
		reviewPacket(true);
		renderActions();

		await waitFor(() =>
			expect(screen.getByRole("alert")).toHaveTextContent("REVIEW_HARD_GATE_BLOCKED: review packet hard gates 未通过"),
		);
		expect(screen.getByRole("button", { name: "批准" })).toBeDisabled();
	});

	it("rejects an invalid packet identity before exposing approval", async () => {
		reviewPacket(false, "not-a-content-hash");
		renderActions();

		await waitFor(() =>
			expect(screen.getByRole("alert")).toHaveTextContent("REVIEW_PACKET_INVALID: review packet bundle hash 无效"),
		);
		expect(screen.getByRole("button", { name: "批准" })).toBeDisabled();
	});

	it("maps typed API failures without leaking ApiError into the strategy feature", async () => {
		server.use(
			http.get("/api/v1/research/experiments/exp-gov/review-packet", () =>
				HttpResponse.json({ detail: "packet unavailable", error_code: "REVIEW_PACKET_UNAVAILABLE" }, { status: 503 }),
			),
		);
		renderActions();

		await waitFor(() =>
			expect(screen.getByRole("alert")).toHaveTextContent("503 REVIEW_PACKET_UNAVAILABLE: packet unavailable"),
		);
		expect(screen.getByRole("button", { name: "批准" })).toBeDisabled();
	});

	it("fails closed when the strategy version has no packet identity", () => {
		renderActions(null);

		expect(screen.getByRole("button", { name: "批准" })).toBeDisabled();
		expect(screen.getByRole("alert")).toHaveTextContent("REVIEW_PACKET_MISSING: 当前策略版本没有绑定 review packet");
	});
});
