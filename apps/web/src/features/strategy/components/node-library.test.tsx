import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { NodeLibrary } from "./node-library";

function renderWithClient(ui: ReactNode) {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("NodeLibrary", () => {
	it("renders node descriptors grouped by category", async () => {
		renderWithClient(<NodeLibrary />);
		// MSW handler /api/v1/research/node-descriptors → mockNodeDescriptorList
		expect(await screen.findByText("Universe")).toBeInTheDocument();
		expect(screen.getByText("Factor Set")).toBeInTheDocument();
		expect(screen.getByText("Trend Filter")).toBeInTheDocument();
		expect(screen.getByText("UNIVERSE")).toBeInTheDocument();
		expect(screen.getByText("FILTER")).toBeInTheDocument();
	});

	it("allows adding only the optional FILTER descriptor", async () => {
		const user = userEvent.setup();
		const onAdd = vi.fn();
		renderWithClient(<NodeLibrary onAdd={onAdd} />);
		await user.click(await screen.findByRole("button", { name: "添加" }));
		expect(onAdd).toHaveBeenCalledWith(
			expect.objectContaining({ nodeType: "builtin.trend_filter", category: "FILTER" }),
		);
		expect(screen.getAllByText("固定槽位")).toHaveLength(7);
	});
});
