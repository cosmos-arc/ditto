import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AlertRow } from "./alert-row";

describe("AlertRow", () => {
	// ── Rendering ──

	it("renders severity dot and title", () => {
		render(<AlertRow severity="warning" title="模型漂移" />);
		expect(screen.getByText("模型漂移")).toBeInTheDocument();
	});

	it("renders with data-slot attribute", () => {
		const { container } = render(
			<AlertRow severity="info" title="数据延迟" />,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root).toHaveAttribute("data-slot", "alert-row");
	});

	it("renders severity attribute", () => {
		const { container } = render(
			<AlertRow severity="critical" title="VaR 突破" />,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root).toHaveAttribute("data-severity", "critical");
	});

	// ── Severity variants ──

	it.each(["critical", "warning", "info"] as const)(
		"renders StatusDot with correct variant for severity=%s",
		(severity) => {
			render(<AlertRow severity={severity} title="Test" />);
			const dot = document.querySelector("[data-slot='status-dot']") as HTMLElement;
			const expectedDotVariant =
				severity === "warning" ? "degraded" : severity;
			expect(dot).toHaveAttribute("data-variant", expectedDotVariant);
		},
	);

	it("applies pulse to critical severity dot", () => {
		render(<AlertRow severity="critical" title="Test" />);
		const dot = document.querySelector("[data-slot='status-dot']") as HTMLElement;
		expect(dot.className).toContain("animate-");
	});

	it("does not apply pulse to warning severity dot", () => {
		render(<AlertRow severity="warning" title="Test" />);
		const dot = document.querySelector("[data-slot='status-dot']") as HTMLElement;
		expect(dot.className).not.toContain("animate-");
	});

	it("does not apply pulse to info severity dot", () => {
		render(<AlertRow severity="info" title="Test" />);
		const dot = document.querySelector("[data-slot='status-dot']") as HTMLElement;
		expect(dot.className).not.toContain("animate-");
	});

	// ── Time display ──

	it("renders time when provided", () => {
		render(<AlertRow severity="info" title="数据延迟" time="5分钟前" />);
		expect(screen.getByText("5分钟前")).toBeInTheDocument();
	});

	it("does not render time element when not provided", () => {
		render(<AlertRow severity="info" title="数据延迟" />);
		expect(screen.queryByText("5分钟前")).not.toBeInTheDocument();
	});

	// ── Click interaction ──

	it("calls onClick when clicked", async () => {
		const user = userEvent.setup();
		const onClick = vi.fn();
		render(
			<AlertRow severity="info" title="数据延迟" onClick={onClick} />,
		);
		await user.click(screen.getByText("数据延迟"));
		expect(onClick).toHaveBeenCalledTimes(1);
	});

	it("applies cursor-pointer when onClick is provided", () => {
		const { container } = render(
			<AlertRow severity="info" title="数据延迟" onClick={() => {}} />,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.className).toContain("cursor-pointer");
	});

	it("does not apply cursor-pointer when onClick is not provided", () => {
		const { container } = render(
			<AlertRow severity="info" title="数据延迟" />,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.className).not.toContain("cursor-pointer");
	});

	// ── className merging ──

	it("merges custom className", () => {
		const { container } = render(
			<AlertRow severity="info" title="Test" className="extra-class" />,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.classList.contains("extra-class")).toBe(true);
	});

	// ── Structure ──

	it("applies flex layout with items-center", () => {
		const { container } = render(
			<AlertRow severity="info" title="Test" />,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.className).toContain("flex");
		expect(root.className).toContain("items-center");
	});
});
