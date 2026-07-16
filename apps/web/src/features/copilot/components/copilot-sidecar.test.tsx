import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/features/shell/components/app-shell";
import { aiHandlers } from "@/mocks/handlers/ai";
import { server } from "@/mocks/server";

const mockUseLocation = vi.fn().mockReturnValue({ pathname: "/" });
const mockUseMatches = vi.fn().mockReturnValue([]);

vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");

	return {
		...actual,
		useLocation: () => mockUseLocation(),
		useMatches: () => mockUseMatches(),
		Link: ({ children, to, ...props }: { children: React.ReactNode; to: string; [key: string]: unknown }) => (
			<a href={to} {...props}>
				{children}
			</a>
		),
	};
});

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

describe("Copilot sidecar", () => {
	beforeEach(() => {
		server.use(...aiHandlers);
		mockUseLocation.mockReturnValue({ pathname: "/" });
		mockUseMatches.mockReturnValue([]);
	});

	it("opens from the shell header command and closes from the close button", async () => {
		const user = userEvent.setup();
		render(<AppShell>content</AppShell>, { wrapper: createWrapper() });

		expect(screen.queryByRole("dialog", { name: "Copilot" })).not.toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: "打开 Copilot" }));

		expect(screen.getByRole("dialog", { name: "Copilot" })).toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: "关闭 Copilot" }));

		expect(screen.queryByRole("dialog", { name: "Copilot" })).not.toBeInTheDocument();
	});

	it("closes on Escape", async () => {
		const user = userEvent.setup();
		render(<AppShell>content</AppShell>, { wrapper: createWrapper() });

		await user.click(screen.getByRole("button", { name: "打开 Copilot" }));
		expect(screen.getByRole("dialog", { name: "Copilot" })).toBeInTheDocument();

		await user.keyboard("{Escape}");

		expect(screen.queryByRole("dialog", { name: "Copilot" })).not.toBeInTheDocument();
	});
});
