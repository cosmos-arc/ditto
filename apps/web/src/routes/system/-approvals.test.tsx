import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const routeState = vi.hoisted(() => ({
	navigate: vi.fn(),
	parseSearch: vi.fn((search: Record<string, unknown>) => ({ ...search, tab: "approvals" })),
	search: { offset: 20, selected: "approval-1", status: "pending", tab: "approvals" },
}));

vi.mock("@tanstack/react-router", () => ({
	createFileRoute: () => (options: Readonly<Record<string, unknown>>) => ({
		options,
		useNavigate: () => routeState.navigate,
		useSearch: () => routeState.search,
	}),
}));

vi.mock("@/features/agent", () => ({
	AgentConsolePage: (props: {
		readonly onSearchChange: (next: {
			readonly offset?: number;
			readonly selected?: string;
			readonly status?: string;
		}) => void;
	}) => (
		<>
			<button type="button" onClick={() => props.onSearchChange({ selected: "approval-2", status: "approved" })}>
				Reset approval page
			</button>
			<button
				type="button"
				onClick={() => props.onSearchChange({ offset: 40, selected: "approval-3", status: "rejected" })}
			>
				Keep approval page
			</button>
		</>
	),
	parseAgentConsoleSearch: routeState.parseSearch,
}));

import { Route } from "./approvals";

describe("approval inbox route", () => {
	it("pins search validation and navigation to the approvals surface", () => {
		const validateSearch = Route.options.validateSearch as
			| ((search: Record<string, unknown>) => Record<string, unknown>)
			| undefined;
		if (!validateSearch) throw new Error("expected approval route search validator");
		expect(validateSearch({ tab: "runs", offset: "20" })).toEqual({ tab: "approvals", offset: "20" });
		expect(routeState.parseSearch).toHaveBeenCalledWith(
			{ tab: "runs", offset: "20" },
			{ allowedTabs: ["approvals"], defaultTab: "approvals" },
		);

		const Component = Route.options.component;
		if (!Component) throw new Error("expected approval route component");
		render(<Component />);
		fireEvent.click(screen.getByRole("button", { name: "Reset approval page" }));
		fireEvent.click(screen.getByRole("button", { name: "Keep approval page" }));

		expect(routeState.navigate).toHaveBeenNthCalledWith(1, {
			replace: true,
			search: {
				contextId: undefined,
				contextType: undefined,
				objective: undefined,
				offset: 0,
				selected: "approval-2",
				sessionId: undefined,
				sessionOffset: 0,
				status: "approved",
				tab: "approvals",
			},
		});
		expect(routeState.navigate).toHaveBeenNthCalledWith(
			2,
			expect.objectContaining({ search: expect.objectContaining({ offset: 40 }) }),
		);
	});
});
