import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { ReviewDecisionPanel } from "./review-decision-panel";

function createWrapper() {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

function renderPanel(reviewOutcome: string, hardReviewBlocked = false, bundleHash = "b".repeat(64)) {
	render(
		<ReviewDecisionPanel
			strategyId="s"
			version={1}
			reviewOutcome={reviewOutcome}
			hardReviewBlocked={hardReviewBlocked}
			bundleHash={bundleHash}
		/>,
		{ wrapper: createWrapper() },
	);
}

describe("ReviewDecisionPanel", () => {
	it("pending outcome shows approve and reject, no publish", () => {
		renderPanel("pending");
		expect(screen.getByRole("button", { name: "批准" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "驳回" })).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "发布" })).not.toBeInTheDocument();
	});

	it("hard-gate blocked pending outcome disables approve but preserves reject", () => {
		renderPanel("pending", true);
		expect(screen.getByRole("button", { name: "批准" })).toBeDisabled();
		expect(screen.getByRole("button", { name: "驳回" })).toBeEnabled();
	});

	it("approved outcome with hard-gate passed shows publish and deprecate", () => {
		renderPanel("approved", false);
		expect(screen.getByRole("button", { name: "发布" })).toBeEnabled();
		expect(screen.getByRole("button", { name: "弃用" })).toBeInTheDocument();
	});

	it("approved outcome with hard-gate blocked disables publish", () => {
		renderPanel("approved", true);
		expect(screen.getByRole("button", { name: "发布" })).toBeDisabled();
	});

	it("other outcome shows no action buttons", () => {
		renderPanel("rejected");
		expect(screen.queryByRole("button", { name: "发布" })).not.toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "批准" })).not.toBeInTheDocument();
		expect(screen.getByRole("link", { name: "克隆为新草稿" })).toHaveAttribute("href", "/research/strategies/s/studio");
	});
});
