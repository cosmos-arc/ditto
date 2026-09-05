import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ContextActions } from "@/providers";
import { AppShell } from "@/workflows/app-shell";

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
		expect(screen.getByRole("link", { name: "进入 Research Agent Lab" })).toHaveAttribute(
			"href",
			"/research/agent?tab=runs",
		);
		expect(screen.getByRole("link", { name: "System Agent Ops" })).toHaveAttribute("href", "/system/agent?tab=runs");
		expect(screen.getByRole("link", { name: "Approval Inbox" })).toHaveAttribute(
			"href",
			"/system/approvals?tab=approvals",
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

	it("injects Agent context actions without exposing Agent imports to business features", () => {
		render(
			<AppShell>
				<ContextActions contextId="experiment-7@2" contextType="experiment-revision" evidenceObjective="复核实验证据" />
			</AppShell>,
		);

		const action = screen.getByRole("link", { name: "请求证据分析" });
		const href = new URL(action.getAttribute("href") ?? "", "http://ditto.local");
		expect(Object.fromEntries(href.searchParams)).toEqual({
			contextId: "experiment-7@2",
			contextType: "experiment-revision",
			objective: "复核实验证据",
			tab: "runs",
		});
	});

	it.each([
		["/", "home", "Today"],
		["/markets/a-shares", "markets", "Markets"],
		["/research/factors", "research", "Research"],
		["/portfolio/model", "portfolio", "Portfolio"],
		["/system/jobs", "system", "System"],
	] as const)("binds %s to the %s governed context", async (pathname, domain, label) => {
		mockUseLocation.mockReturnValue({ pathname });
		const user = userEvent.setup();
		render(<AppShell>content</AppShell>);

		await user.click(screen.getByRole("button", { name: "打开 Agent 工作入口" }));

		const sidecar = screen.getByRole("dialog", { name: "Agent 工作入口" });
		expect(sidecar).toHaveAttribute("data-agent-context-domain", domain);
		expect(sidecar).toHaveTextContent(`当前上下文 · ${label}`);
	});
});
