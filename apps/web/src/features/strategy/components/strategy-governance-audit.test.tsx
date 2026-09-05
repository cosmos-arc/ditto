import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { StrategyGovernanceAudit } from "./strategy-governance-audit";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

describe("StrategyGovernanceAudit", () => {
	it("pages by the last server event_id and never injects the current packet hash into an event row", async () => {
		const cursors: Array<string | null> = [];
		server.use(
			http.get("/api/v1/strategies/s/events", ({ request }) => {
				const cursor = new URL(request.url).searchParams.get("after_event_id");
				cursors.push(cursor);
				const events = cursor
					? [
							{
								event_id: "event-3",
								strategy_id: "s",
								target_version: 3,
								event_type: "strategy.activated",
								decision_or_activation_kind: "reactivate",
								actor: "operator",
								reason: "restore",
								occurred_at: "2026-08-01T02:00:00Z",
							},
						]
					: [
							{
								event_id: "event-1",
								strategy_id: "s",
								target_version: 2,
								event_type: "strategy.review_decided",
								decision_or_activation_kind: "approve",
								actor: "reviewer",
								reason: "evidence accepted",
								occurred_at: "2026-08-01T00:00:00Z",
							},
							{
								event_id: "event-2",
								strategy_id: "s",
								target_version: 2,
								event_type: "strategy.activated",
								decision_or_activation_kind: "publish",
								actor: "publisher",
								reason: "promote",
								occurred_at: "2026-08-01T01:00:00Z",
							},
						];
				return HttpResponse.json({ data: events });
			}),
		);

		render(<StrategyGovernanceAudit strategyId="s" currentPacketBundleHash={"f".repeat(64)} pageSize={2} />, {
			wrapper,
		});
		const first = await screen.findByTestId("governance-event-event-1");
		expect(within(first).getByText(/approve/)).toBeInTheDocument();
		expect(within(first).queryByText("f".repeat(64))).not.toBeInTheDocument();
		expect(screen.getByText(/event row itself has no persisted bundle association/i)).toBeInTheDocument();

		await userEvent.click(screen.getByRole("button", { name: "加载更多治理事件" }));
		expect(await screen.findByTestId("governance-event-event-3")).toBeInTheDocument();
		expect(cursors).toEqual([null, "event-2"]);
	});
});
