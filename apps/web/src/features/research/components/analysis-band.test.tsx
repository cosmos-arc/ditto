import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AnalysisBand } from "./analysis-band";

describe("AnalysisBand", () => {
	it("renders data-slot=analysis-band on root element", () => {
		render(<AnalysisBand />);
		const root = document.querySelector("[data-slot='analysis-band']");
		expect(root).toBeInTheDocument();
	});

	it("renders 4 tab buttons", () => {
		render(<AnalysisBand />);
		const tabs = screen.getAllByRole("tab");
		expect(tabs).toHaveLength(4);
	});

	it("shows tab labels: IC Trends, 因子宽度, 相关性, 笔记", () => {
		render(<AnalysisBand />);
		expect(screen.getByRole("tab", { name: "IC Trends" })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: "因子宽度" })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: "相关性" })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: "笔记" })).toBeInTheDocument();
	});

	it("defaults to IC Trends tab as active", () => {
		render(<AnalysisBand />);
		const activeTab = screen.getByRole("tab", { name: "IC Trends" });
		expect(activeTab).toHaveAttribute("aria-selected", "true");
	});

	it("renders 3 Metric strips on IC Trends tab", () => {
		render(<AnalysisBand />);
		const metrics = screen.getAllByTestId("metric-root");
		expect(metrics).toHaveLength(3);
	});

	it("shows IC均值, IC_IR, IC胜率 metric labels", () => {
		render(<AnalysisBand />);
		expect(screen.getByText("IC均值")).toBeInTheDocument();
		expect(screen.getByText("IC_IR")).toBeInTheDocument();
		expect(screen.getByText("IC胜率")).toBeInTheDocument();
	});

	it("switches to 因子宽度 tab on click", async () => {
		const user = userEvent.setup();
		render(<AnalysisBand />);

		await user.click(screen.getByRole("tab", { name: "因子宽度" }));

		expect(screen.getByRole("tab", { name: "因子宽度" })).toHaveAttribute("aria-selected", "true");
		expect(screen.getByRole("tab", { name: "IC Trends" })).toHaveAttribute("aria-selected", "false");
	});

	it("renders SVG bar chart on 因子宽度 tab", async () => {
		const user = userEvent.setup();
		render(<AnalysisBand />);

		await user.click(screen.getByRole("tab", { name: "因子宽度" }));

		// SVG with bars inside the tab panel
		const panel = screen.getByRole("tabpanel");
		const bars = panel.querySelectorAll("rect[data-bar]");
		expect(bars.length).toBeGreaterThan(0);
	});

	it("switches to 相关性 tab and renders 5x5 heatmap grid", async () => {
		const user = userEvent.setup();
		render(<AnalysisBand />);

		await user.click(screen.getByRole("tab", { name: "相关性" }));

		const panel = screen.getByRole("tabpanel");
		const cells = panel.querySelectorAll("[data-heatmap-cell]");
		// 5x5 = 25 cells
		expect(cells).toHaveLength(25);
	});

	it("heatmap cells expose correlation tone classes and labels", async () => {
		const user = userEvent.setup();
		render(<AnalysisBand />);

		await user.click(screen.getByRole("tab", { name: "相关性" }));

		const panel = screen.getByRole("tabpanel");
		const firstCell = panel.querySelector("[data-heatmap-cell]");
		expect(firstCell).toBeInTheDocument();
		expect(firstCell).toHaveAttribute("data-correlation-tone");
		expect(firstCell).toHaveAttribute("aria-label", expect.stringContaining("相关系数"));
	});

	it("switches to 笔记 tab and renders note items", async () => {
		const user = userEvent.setup();
		render(<AnalysisBand />);

		await user.click(screen.getByRole("tab", { name: "笔记" }));

		const panel = screen.getByRole("tabpanel");
		const notes = panel.querySelectorAll("[data-note-item]");
		expect(notes.length).toBeGreaterThan(0);
	});

	it("notes display text and time", async () => {
		const user = userEvent.setup();
		render(<AnalysisBand />);

		await user.click(screen.getByRole("tab", { name: "笔记" }));

		const panel = screen.getByRole("tabpanel");
		const firstNote = panel.querySelector("[data-note-item]");
		expect(firstNote?.textContent).toBeTruthy();
	});

	it("only one tab panel is visible at a time", async () => {
		const user = userEvent.setup();
		render(<AnalysisBand />);

		// Initially only IC Trends panel is visible
		expect(screen.getAllByRole("tabpanel")).toHaveLength(1);

		await user.click(screen.getByRole("tab", { name: "笔记" }));

		// Still only one tabpanel
		expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
	});
});
