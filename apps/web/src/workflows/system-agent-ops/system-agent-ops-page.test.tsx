import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { aiHandlers } from "@/mocks/handlers/ai";
import { server } from "@/mocks/server";
import { SystemAgentOpsPage } from "./system-agent-ops-page";

function createWrapper() {
	const queryClient = new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
		},
	});
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => {
	server.use(...aiHandlers);
});

describe("System Agent Ops workflow page contract", () => {
	it("covers the governed route composition", () => {
		render(<SystemAgentOpsPage />, { wrapper: createWrapper() });

		expect(screen.getByRole("region", { name: "System Agent Ops" })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: "Runs" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "新建 Run" })).toBeDisabled();
	});
});
