import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DecisionBanner } from "./decision-banner";

const BASE_PROPS = {
	primary: {
		label: "今日盈亏",
		value: "+¥86,472.50",
		sub: "+0.34% · 总权益 ¥25,432,180",
		trend: "up" as const,
		sparkline: [40, 35, 42, 38, 45, 50, 48, 55, 60] as const,
	},
	judgment: {
		text: "波动回落，北向转暖，但局部拥挤。",
		regime: { label: "风险偏好", variant: "regime-on" as const },
		metrics: [
			{ label: "杠杆率", value: "1.2x" },
			{ label: "回撤", value: "-3.8%", trend: "down" as const },
		],
	},
	actions: [
		{ label: "查看信号总览", variant: "primary" as const },
		{ label: "进入研究", variant: "secondary" as const },
		{ label: "查看风控", variant: "ghost" as const },
	],
};

describe("DecisionBanner", () => {
	// ── Rendering ──

	it("renders primary label", () => {
		render(<DecisionBanner {...BASE_PROPS} />);
		expect(screen.getByText("今日盈亏")).toBeInTheDocument();
	});

	it("renders primary value", () => {
		render(<DecisionBanner {...BASE_PROPS} />);
		// Metric equity variant prepends trend arrow
		expect(screen.getByText(/¥86,472\.50/)).toBeInTheDocument();
	});

	it("renders primary sub text", () => {
		render(<DecisionBanner {...BASE_PROPS} />);
		expect(screen.getByText("+0.34% · 总权益 ¥25,432,180")).toBeInTheDocument();
	});

	it("renders judgment text", () => {
		render(<DecisionBanner {...BASE_PROPS} />);
		expect(screen.getByText("波动回落，北向转暖，但局部拥挤。")).toBeInTheDocument();
	});

	it("renders regime badge", () => {
		render(<DecisionBanner {...BASE_PROPS} />);
		expect(screen.getByText("风险偏好")).toBeInTheDocument();
	});

	it("renders judgment metrics", () => {
		render(<DecisionBanner {...BASE_PROPS} />);
		expect(screen.getByText("杠杆率")).toBeInTheDocument();
		expect(screen.getByText("1.2x")).toBeInTheDocument();
	});

	it("renders action buttons", () => {
		render(<DecisionBanner {...BASE_PROPS} />);
		expect(screen.getByText("查看信号总览")).toBeInTheDocument();
		expect(screen.getByText("进入研究")).toBeInTheDocument();
		expect(screen.getByText("查看风控")).toBeInTheDocument();
	});

	// ── Structure ──

	it("renders with data-slot attribute", () => {
		render(<DecisionBanner {...BASE_PROPS} />);
		expect(document.querySelector("[data-slot='decision-banner']")).toBeInTheDocument();
	});

	it("renders 3-column grid layout", () => {
		render(<DecisionBanner {...BASE_PROPS} />);
		const banner = document.querySelector("[data-slot='decision-banner']") as HTMLElement;
		expect(banner.className).toContain("grid");
	});

	// ── Minimal props ──

	it("renders without optional props", () => {
		render(
			<DecisionBanner
				primary={{ label: "PnL", value: 0 }}
				judgment={{ text: "Test judgment", metrics: [] }}
			/>,
		);
		expect(screen.getByText("PnL")).toBeInTheDocument();
		expect(screen.getByText("Test judgment")).toBeInTheDocument();
	});

	// ── Click actions ──

	it("calls action onClick when clicked", async () => {
		const user = userEvent.setup();
		const onClick = vi.fn();
		render(
			<DecisionBanner
				{...BASE_PROPS}
				actions={[{ label: "Action", variant: "primary", onClick }]}
			/>,
		);
		await user.click(screen.getByText("Action"));
		expect(onClick).toHaveBeenCalledTimes(1);
	});

	// ── className merging ──

	it("merges custom className", () => {
		render(
			<DecisionBanner {...BASE_PROPS} className="extra-class" />,
		);
		const banner = document.querySelector("[data-slot='decision-banner']") as HTMLElement;
		expect(banner.classList.contains("extra-class")).toBe(true);
	});
});
