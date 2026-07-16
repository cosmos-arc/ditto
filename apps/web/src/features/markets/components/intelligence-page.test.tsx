import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { intelligenceHandlers } from "@/mocks/handlers/intelligence";
import { marketsHandlers } from "@/mocks/handlers/markets";
import { server } from "@/mocks/server";
import { IntelligencePage } from "./intelligence-page";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
}

function createWrapper() {
	const qc = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => server.use(...marketsHandlers, ...intelligenceHandlers));

describe("IntelligencePage — Tab navigation", () => {
	it("shows 资金流向 tab by default", async () => {
		render(<IntelligencePage />, { wrapper: createWrapper() });

		const flowTab = await screen.findByRole("tab", { name: "资金流向" });
		expect(flowTab).toHaveAttribute("data-state", "active");
	});

	it("renders three tab triggers", async () => {
		render(<IntelligencePage />, { wrapper: createWrapper() });

		await expect(screen.findByRole("tab", { name: "资金流向" })).resolves.toBeInTheDocument();
		await expect(screen.findByRole("tab", { name: "宏观指标" })).resolves.toBeInTheDocument();
		await expect(screen.findByRole("tab", { name: "基本面" })).resolves.toBeInTheDocument();
	});

	it("switches to 宏观指标 tab on click", async () => {
		const user = userEvent.setup();
		render(<IntelligencePage />, { wrapper: createWrapper() });

		const macroTab = await screen.findByRole("tab", { name: "宏观指标" });
		await user.click(macroTab);

		expect(macroTab).toHaveAttribute("data-state", "active");
		await expect(screen.findByText("PMI 制造业")).resolves.toBeInTheDocument();
	});

	it("switches to 基本面 tab on click", async () => {
		const user = userEvent.setup();
		render(<IntelligencePage />, { wrapper: createWrapper() });

		const fundamentalsTab = await screen.findByRole("tab", { name: "基本面" });
		await user.click(fundamentalsTab);

		expect(fundamentalsTab).toHaveAttribute("data-state", "active");
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
	});

	it("renders default tab content (资金流向)", async () => {
		render(<IntelligencePage />, { wrapper: createWrapper() });

		await expect(screen.findByText("板块排名")).resolves.toBeInTheDocument();
	});

	it("renders AI 解读 sidebar panel", async () => {
		render(<IntelligencePage />, { wrapper: createWrapper() });

		await expect(screen.findByText("AI 解读")).resolves.toBeInTheDocument();
	});
});
