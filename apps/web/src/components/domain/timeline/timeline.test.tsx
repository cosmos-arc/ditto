import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Timeline } from "./timeline";

const SAMPLE_ITEMS = [
	{
		id: "1",
		title: "组合 VaR 突破 95% 分位",
		time: "09:32",
		severity: "critical" as const,
		status: "triggered" as const,
	},
	{
		id: "2",
		title: "中信证券 API 连接恢复",
		time: "10:15",
		description: "自动重连成功",
		severity: "ok" as const,
		status: "resolved" as const,
	},
	{
		id: "3",
		title: "模型漂移检测",
		time: "11:45",
		severity: "warn" as const,
		status: "monitoring" as const,
	},
] as const;

describe("Timeline", () => {
	// ── Rendering ──

	it("renders items list", () => {
		render(<Timeline items={[SAMPLE_ITEMS[0]]} />);
		expect(screen.getByText("组合 VaR 突破 95% 分位")).toBeInTheDocument();
	});

	it("renders all items", () => {
		render(<Timeline items={[...SAMPLE_ITEMS]} />);
		expect(screen.getByText("组合 VaR 突破 95% 分位")).toBeInTheDocument();
		expect(screen.getByText("中信证券 API 连接恢复")).toBeInTheDocument();
		expect(screen.getByText("模型漂移检测")).toBeInTheDocument();
	});

	it("renders time for each item", () => {
		render(<Timeline items={[SAMPLE_ITEMS[0]]} />);
		expect(screen.getByText("09:32")).toBeInTheDocument();
	});

	it("renders description when provided", () => {
		render(<Timeline items={[SAMPLE_ITEMS[1]]} />);
		expect(screen.getByText("自动重连成功")).toBeInTheDocument();
	});

	it("renders with data-slot attribute", () => {
		const { container } = render(<Timeline items={[SAMPLE_ITEMS[0]]} />);
		const root = container.firstElementChild as HTMLElement;
		expect(root).toHaveAttribute("data-slot", "timeline");
	});

	// ── Empty state ──

	it("renders empty container when items is empty", () => {
		const { container } = render(<Timeline items={[]} />);
		const root = container.firstElementChild as HTMLElement;
		expect(root).toBeInTheDocument();
		expect(root.children).toHaveLength(0);
	});

	// ── Status badge ──

	it("renders status text when status is provided", () => {
		render(<Timeline items={[SAMPLE_ITEMS[0]]} />);
		expect(screen.getByText("触发")).toBeInTheDocument();
	});

	// ── Severity dot ──

	it("renders StatusDot for severity=critical", () => {
		render(<Timeline items={[SAMPLE_ITEMS[0]]} />);
		const dot = document.querySelector("[data-slot='status-dot']") as HTMLElement;
		expect(dot).toBeInTheDocument();
		expect(dot).toHaveAttribute("data-variant", "critical");
	});

	it("renders StatusDot for severity=ok", () => {
		render(<Timeline items={[SAMPLE_ITEMS[1]]} />);
		const dot = document.querySelector("[data-slot='status-dot']") as HTMLElement;
		expect(dot).toBeInTheDocument();
		expect(dot).toHaveAttribute("data-variant", "healthy");
	});

	it("renders StatusDot for severity=warn", () => {
		render(<Timeline items={[SAMPLE_ITEMS[2]]} />);
		const dot = document.querySelector("[data-slot='status-dot']") as HTMLElement;
		expect(dot).toBeInTheDocument();
		expect(dot).toHaveAttribute("data-variant", "degraded");
	});

	// ── className merging ──

	it("merges custom className", () => {
		const { container } = render(<Timeline items={[SAMPLE_ITEMS[0]]} className="extra-class" />);
		const root = container.firstElementChild as HTMLElement;
		expect(root.classList.contains("extra-class")).toBe(true);
	});
});
