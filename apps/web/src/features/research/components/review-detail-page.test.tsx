import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { mockReviewPacket } from "@/mocks/fixtures/review-live";
import { server } from "@/mocks/server";
import { ReviewDetailPage } from "@/workflows/review-detail";

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
	it("keeps the default governed mock packet aligned with its queue version", async () => {
		render(<ReviewDetailPage experimentId="exp-rotation-v4" strategyId="seed_etf_industry_rotation" version={4} />, {
			wrapper,
		});

		expect(await screen.findByRole("button", { name: "发布" })).toBeEnabled();
		expect(screen.getByTestId("review-detail-meta")).toHaveTextContent(/approved/);
		expect(screen.getByTestId("review-detail-meta")).not.toHaveTextContent(/unknown/);
	});

	it("organizes the governed packet as a decision workbench without turning soft statistics into PASS", async () => {
		registerReviewHandlers();
		const user = userEvent.setup();
		render(<ReviewDetailPage experimentId="exp-review" strategyId="s" version={2} />, {
			wrapper,
		});

		expect(screen.getByRole("region", { name: "审查决策工作台" })).toBeInTheDocument();
		expect(await screen.findByRole("navigation", { name: "审查工作台导航" })).toBeInTheDocument();
		expect(screen.getByText("Decision Banner")).toBeInTheDocument();
		expect(screen.getByText("Hard Gates")).toBeInTheDocument();
		expect(screen.getByText("Decision Form")).toBeInTheDocument();
		expect(screen.queryByText("Statistical Evidence")).not.toBeInTheDocument();

		await user.click(screen.getByRole("tab", { name: "证据与差异" }));
		const statistical = screen.getByText("Statistical Evidence").closest('[data-slot="context-section"]');
		expect(statistical).not.toBeNull();
		expect((statistical as HTMLElement).querySelector('[data-slot="status-badge"]')).not.toBeInTheDocument();
		expect(within(statistical as HTMLElement).getByText(/no automatic pass/i)).toBeInTheDocument();
		expect(screen.getByText(/Technology/)).toBeInTheDocument();
		expect(screen.getByText(/large/)).toBeInTheDocument();

		await user.click(screen.getByRole("tab", { name: "血统与影响" }));
		expect(screen.getByText("Lineage/Artifacts")).toBeInTheDocument();
		expect(screen.getByText("R1 Impact")).toBeInTheDocument();

		await user.click(screen.getByRole("tab", { name: "治理审计" }));
		expect(screen.getByRole("region", { name: "Governance Audit" })).toBeInTheDocument();
		expect(screen.getByTestId("review-detail-bottom")).toHaveTextContent(/bundle/i);
		expect(screen.getByTestId("review-detail-bottom")).toHaveTextContent(mockReviewPacket.bundle_hash);
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
