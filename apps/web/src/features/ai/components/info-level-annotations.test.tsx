import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { aiHandlers } from "@/mocks/handlers/ai";
import { AiMainContent } from "./ai-main-content";
import { AgentsPage } from "./agents-page";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
		},
	});
}

function createWrapper() {
	const queryClient = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => {
	server.use(...aiHandlers);
});

describe("AiMainContent info-level annotations", () => {
	it("annotates all 4 tab panels as L1", async () => {
		render(<AiMainContent />, { wrapper: createWrapper() });

		// Overview tab is active by default
		await screen.findByText("Agent 计划");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l1UnitNames).toContain("ai-overview");
		expect(l1Units).toHaveLength(1);

		// Switch to Agents tab
		await userEvent.click(screen.getByRole("tab", { name: "Agents" }));
		const l1AfterAgents = document.querySelectorAll("[data-info-level='l1']");
		expect(Array.from(l1AfterAgents).map((el) => el.getAttribute("data-info-unit"))).toContain("ai-agents");

		// Switch to Copilot tab
		await userEvent.click(screen.getByRole("tab", { name: "Copilot" }));
		const l1AfterCopilot = document.querySelectorAll("[data-info-level='l1']");
		expect(Array.from(l1AfterCopilot).map((el) => el.getAttribute("data-info-unit"))).toContain("ai-copilot");

		// Switch to Settings tab
		await userEvent.click(screen.getByRole("tab", { name: "Settings" }));
		const l1AfterSettings = document.querySelectorAll("[data-info-level='l1']");
		expect(Array.from(l1AfterSettings).map((el) => el.getAttribute("data-info-unit"))).toContain("ai-settings");
	});

	it("has no L2 information units", async () => {
		render(<AiMainContent />, { wrapper: createWrapper() });

		await screen.findByText("Agent 计划");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		expect(l2Units).toHaveLength(0);
	});
});

// ── AgentsPage: 4 L1, 2 L2 ──

describe("AgentsPage info-level annotations", () => {
	it("annotates 4 L1 information units", async () => {
		render(<AgentsPage />, { wrapper: createWrapper() });

		await screen.findByText("目标");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l1UnitNames).toContain("agent-objective");
		expect(l1UnitNames).toContain("agent-constraints");
		expect(l1UnitNames).toContain("agent-scope");
		expect(l1UnitNames).toContain("agent-run-status");
		expect(l1Units).toHaveLength(4);
	});

	it("annotates 2 L2 information units", async () => {
		render(<AgentsPage />, { wrapper: createWrapper() });

		await screen.findByText("目标");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l2UnitNames).toContain("agent-related-findings");
		expect(l2UnitNames).toContain("agent-findings-list");
		expect(l2Units).toHaveLength(2);
	});
});
