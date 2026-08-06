import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { mockReviewPacket } from "@/mocks/fixtures/review-live";
import { server } from "@/mocks/server";
import { ReviewDetailPage } from "./review-detail-page";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

function registerReviewHandlers(hardReviewBlocked = false, reviewOutcome = "pending") {
	server.use(
		http.get("/api/v1/research/experiments/exp-review/review-packet", () =>
			HttpResponse.json({
				data: {
					...mockReviewPacket,
					experiment_id: "exp-review",
					hard_review_blocked: hardReviewBlocked,
					selection_exposure: {
						lane: "stock",
						applicability: "applicable",
						industry_weights: [{ key: "Technology", weight: 0.42 }],
						size_bucket_weights: [{ key: "large", weight: 0.61 }],
						artifact_refs: mockReviewPacket.selection_trace_artifact_refs,
					},
				},
			}),
		),
		http.get("/api/v1/strategies/s/versions", () =>
			HttpResponse.json({
				data: [
					{
						strategy_id: "s",
						version: 2,
						parent_version: 1,
						spec_hash: "a".repeat(64),
						state: "review",
						review_outcome: reviewOutcome,
						created_at: "2026-08-01T00:00:00Z",
						experiment_id: "exp-review",
					},
				],
			}),
		),
		http.get("/api/v1/strategies/s/versions/2/diff", () =>
			HttpResponse.json({
				data: {
					strategy_id: "s",
					version: 2,
					parent_version: 1,
					base_spec_hash: "b".repeat(64),
					target_spec_hash: "a".repeat(64),
					changed: true,
					changes: [{ path: "/selector/top_k", op: "replace", old: 10, new: 8 }],
				},
			}),
		),
		http.get("/api/v1/strategies/s/events", () => HttpResponse.json({ data: [] })),
	);
}

describe("ReviewDetailPage", () => {
	it("renders the frozen evidence sections in order without turning soft statistics into PASS", async () => {
		registerReviewHandlers();
		const { container } = render(<ReviewDetailPage experimentId="exp-review" strategyId="s" version={2} />, {
			wrapper,
		});

		await screen.findByText("Decision Banner");
		const sectionTitles = Array.from(container.querySelectorAll('[data-slot="context-section-header"]')).map((node) =>
			node.querySelector("span")?.textContent?.trim(),
		);
		expect(sectionTitles.slice(0, 9)).toEqual([
			"Decision Banner",
			"Hard Gates",
			"Statistical Evidence",
			"Spec Diff",
			"Candidate Rationale",
			"Selection/Exposure Evidence",
			"Lineage/Artifacts",
			"R1 Impact",
			"Decision Form",
		]);
		const statistical = screen.getByText("Statistical Evidence").closest('[data-slot="context-section"]');
		expect(statistical).not.toBeNull();
		expect((statistical as HTMLElement).querySelector('[data-slot="status-badge"]')).not.toBeInTheDocument();
		expect(within(statistical as HTMLElement).getByText(/no automatic pass/i)).toBeInTheDocument();
		expect(screen.getByText(/Technology/)).toBeInTheDocument();
		expect(screen.getByText(/large/)).toBeInTheDocument();
	});

	it("fails closed on a hard gate and disables approve", async () => {
		registerReviewHandlers(true);
		render(<ReviewDetailPage experimentId="exp-review" strategyId="s" version={2} />, { wrapper });

		expect(await screen.findByRole("button", { name: "批准" })).toBeDisabled();
		expect(screen.getByRole("button", { name: "驳回" })).toBeEnabled();
	});

	it("shows a typed packet error with retry instead of a prototype fallback", async () => {
		server.use(
			http.get("/api/v1/research/experiments/exp-review/review-packet", () =>
				HttpResponse.json({ detail: "packet unavailable", error_code: "REVIEW_PACKET_UNAVAILABLE" }, { status: 503 }),
			),
		);
		render(<ReviewDetailPage experimentId="exp-review" strategyId="s" version={2} />, { wrapper });

		expect(await screen.findByRole("alert")).toHaveTextContent(/503 REVIEW_PACKET_UNAVAILABLE/);
		expect(screen.getByRole("button", { name: "重试审查包" })).toBeInTheDocument();
		expect(screen.queryByText(/prototype/i)).not.toBeInTheDocument();
	});
});
