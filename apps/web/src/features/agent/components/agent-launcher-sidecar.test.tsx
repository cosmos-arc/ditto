import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/features/shell/components/app-shell";

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

describe("Agent launcher sidecar", () => {
	beforeEach(() => {
		mockUseLocation.mockReturnValue({ pathname: "/" });
		mockUseMatches.mockReturnValue([]);
	});

	it("opens the governed entry, exposes canonical task links, and returns focus", async () => {
		const user = userEvent.setup();
		render(<AppShell>content</AppShell>);
		const trigger = screen.getByRole("button", { name: "打开 Agent 工作入口" });

		await user.click(trigger);

		expect(screen.getByRole("dialog", { name: "Agent 工作入口" })).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "进入 Agent Console" })).toHaveAttribute(
			"href",
			"/platform/agents?tab=runs",
		);
		expect(screen.queryByText("Copilot")).not.toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: "关闭 Agent 工作入口" }));

		expect(screen.queryByRole("dialog", { name: "Agent 工作入口" })).not.toBeInTheDocument();
		expect(trigger).toHaveFocus();
	});

	it("closes on Escape", async () => {
		const user = userEvent.setup();
		render(<AppShell>content</AppShell>);

		await user.click(screen.getByRole("button", { name: "打开 Agent 工作入口" }));
		await user.keyboard("{Escape}");

		expect(screen.queryByRole("dialog", { name: "Agent 工作入口" })).not.toBeInTheDocument();
	});
});
