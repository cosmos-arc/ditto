import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import type { StrategyLifecycleState, StrategyVersion } from "@/types/strategy";
import { GovernanceActions } from "./governance-actions";

function makeVersion(lifecycleState: StrategyLifecycleState): StrategyVersion {
	return {
		strategyId: "s",
		version: 1,
		parentVersion: null,
		specHash: "h",
		state: lifecycleState,
		lifecycleState,
		reviewOutcome: "pending",
		createdAt: "2026-01-01T00:00:00Z",
	};
}

function createWrapper() {
	const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

function renderActions(lifecycleState: StrategyLifecycleState, expectedPointerRevision: number | null = null) {
	render(
		<GovernanceActions
			strategyId="s"
			version={makeVersion(lifecycleState)}
			expectedPointerRevision={expectedPointerRevision}
		/>,
		{ wrapper: createWrapper() },
	);
}

describe("GovernanceActions", () => {
	it("draft state shows a submit-review action", () => {
		renderActions("draft");
		expect(screen.getByRole("button", { name: "提交审查" })).toBeInTheDocument();
	});

	it("review state shows approve and reject actions", () => {
		renderActions("review");
		expect(screen.getByRole("button", { name: "批准" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "驳回" })).toBeInTheDocument();
	});

	it("approved state shows deprecate only (publish lives on review-detail)", () => {
		renderActions("approved");
		expect(screen.getByRole("button", { name: "弃用" })).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "发布" })).not.toBeInTheDocument();
	});

	it("published state with a pointer revision shows reactivate", () => {
		renderActions("published", 2);
		expect(screen.getByRole("button", { name: "重新激活" })).toBeInTheDocument();
	});

	it("published state without a pointer revision hides reactivate", () => {
		renderActions("published", null);
		expect(screen.queryByRole("button", { name: "重新激活" })).not.toBeInTheDocument();
	});

	it("deprecated state shows no actions", () => {
		renderActions("deprecated");
		expect(screen.queryByRole("button")).not.toBeInTheDocument();
	});

	it("clicking a decision action opens the dialog with confirm disabled until filled", async () => {
		renderActions("draft");
		await userEvent.click(screen.getByRole("button", { name: "提交审查" }));

		expect(screen.getByRole("heading", { name: "提交审查" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "确认提交" })).toBeDisabled();
	});
});
