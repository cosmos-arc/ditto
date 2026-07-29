import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
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
		expect(await screen.findByText("股票池过滤")).toBeInTheDocument();
		expect(screen.getByText("因子合成")).toBeInTheDocument();
		expect(screen.getByText("Top-K 选取")).toBeInTheDocument();
		expect(screen.getByText("UNIVERSE")).toBeInTheDocument();
		expect(screen.getByText("SCORER")).toBeInTheDocument();
		expect(screen.getByText("SELECTOR")).toBeInTheDocument();
	});
});
