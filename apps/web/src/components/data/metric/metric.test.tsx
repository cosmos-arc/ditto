import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Metric } from "./metric";

describe("Metric", () => {
	/* ── 基础渲染 ── */

	it("renders label, value, and sub text", () => {
		render(<Metric label="Price" value={1234.56} sub="+2.3%" />);
		expect(screen.getByText("Price")).toBeInTheDocument();
		expect(screen.getByText("1,234.56")).toBeInTheDocument();
		expect(screen.getByText("+2.3%")).toBeInTheDocument();
	});

	it("renders without sub when sub is omitted", () => {
		render(<Metric label="Price" value={100} />);
		expect(screen.getByText("Price")).toBeInTheDocument();
		expect(screen.getByText("100")).toBeInTheDocument();
		expect(screen.queryByText("+2.3%")).not.toBeInTheDocument();
	});

	it("formats number values with thousand separators", () => {
		render(<Metric label="Volume" value={12345678} />);
		expect(screen.getByText("12,345,678")).toBeInTheDocument();
	});

	it("renders string values as-is", () => {
		render(<Metric label="Status" value="Active" />);
		expect(screen.getByText("Active")).toBeInTheDocument();
	});

	it("has data-slot='metric' on root element", () => {
		render(<Metric label="L" value={1} />);
		expect(screen.getByTestId("metric-root")).toHaveAttribute("data-slot", "metric");
	});

	/* ── variant: standard (default) ── */

	it("renders variant=standard with label, value, sub vertically stacked", () => {
		render(<Metric label="PnL" value={5000} sub="+1.2%" variant="standard" />);
		const root = screen.getByTestId("metric-root");
		expect(root).toHaveAttribute("data-variant", "standard");

		// Vertical layout: flex-col
		const label = screen.getByText("PnL");
		expect(label.className).toContain("uppercase");
		expect(label.className).toContain("text-sm");
	});

	it("renders variant=standard with semibold value", () => {
		render(<Metric label="A" value={42} variant="standard" />);
		const value = screen.getByText("42");
		expect(value.className).toContain("font-semibold");
	});

	/* ── variant: strip ── */

	it("renders variant=strip with label and value horizontally", () => {
		render(<Metric label="Vol" value={1234} variant="strip" />);
		const root = screen.getByTestId("metric-root");
		expect(root).toHaveAttribute("data-variant", "strip");

		// Horizontal layout: flex-row
		const label = screen.getByText("Vol");
		expect(label.className).toContain("text-sm");

		const value = screen.getByText("1,234");
		expect(value.className).toContain("font-medium");
	});

	/* ── variant: equity ── */

	it("renders variant=equity with large value font", () => {
		render(<Metric label="NAV" value={102400} sub="Sub item" variant="equity" />);
		const root = screen.getByTestId("metric-root");
		expect(root).toHaveAttribute("data-variant", "equity");

		const value = screen.getByText("102,400");
		expect(value.className).toContain("text-3xl");
		expect(value.className).toContain("font-semibold");
	});

	it("renders variant=equity sub as multiple lines", () => {
		render(<Metric label="Fund" value={100} sub={["+5.2%", "YTD"]} variant="equity" />);
		expect(screen.getByText("+5.2%")).toBeInTheDocument();
		expect(screen.getByText("YTD")).toBeInTheDocument();
	});

	/* ── size prop ── */

	it("renders size=sm with value at 14px", () => {
		render(<Metric label="A" value={1} size="sm" />);
		const root = screen.getByTestId("metric-root");
		expect(root).toHaveAttribute("data-size", "sm");

		const value = screen.getByText("1");
		expect(value.className).toContain("text-md");
	});

	it("renders size=md with value at 16px", () => {
		render(<Metric label="A" value={1} size="md" />);
		const root = screen.getByTestId("metric-root");
		expect(root).toHaveAttribute("data-size", "md");

		const value = screen.getByText("1");
		expect(value.className).toContain("text-lg");
	});

	it("renders size=lg with value at 24px", () => {
		render(<Metric label="A" value={1} size="lg" />);
		const root = screen.getByTestId("metric-root");
		expect(root).toHaveAttribute("data-size", "lg");

		const value = screen.getByText("1");
		expect(value.className).toContain("text-3xl");
	});

	it("defaults size to md", () => {
		render(<Metric label="A" value={1} />);
		const root = screen.getByTestId("metric-root");
		expect(root).toHaveAttribute("data-size", "md");
	});

	/* ── trend prop ── */

	it("renders trend='up' with up arrow and market-up color", () => {
		render(<Metric label="Chg" value={3.5} trend="up" />);
		const trend = screen.getByText("▲ 3.5");
		expect(trend.className).toContain("text-(--color-market-up)");
	});

	it("renders trend='down' with down arrow and market-down color", () => {
		render(<Metric label="Chg" value={-1.2} trend="down" />);
		const trend = screen.getByText("▼ -1.2");
		expect(trend.className).toContain("text-(--color-market-down)");
	});

	it("renders trend='flat' with dash and muted color", () => {
		render(<Metric label="Chg" value={0} trend="flat" />);
		const trend = screen.getByText("— 0");
		expect(trend.className).toContain("text-(--color-foreground-muted)");
	});

	it("does not render trend indicator when trend is undefined", () => {
		render(<Metric label="Chg" value={1} />);
		expect(screen.queryByText("▲ 1")).not.toBeInTheDocument();
		expect(screen.queryByText("▼ 1")).not.toBeInTheDocument();
		expect(screen.queryByText("— 1")).not.toBeInTheDocument();
	});

	/* ── sparkline prop ── */

	it("renders Sparkline when sparkline prop is provided", () => {
		render(<Metric label="Price" value={100} sparkline={[1, 2, 3, 4, 5]} />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg).toBeInTheDocument();
		expect(svg).toHaveAttribute("data-slot", "sparkline");
	});

	it("does not render Sparkline when sparkline prop is omitted", () => {
		render(<Metric label="Price" value={100} />);
		expect(screen.queryByRole("img", { hidden: true })).not.toBeInTheDocument();
	});

	/* ── className passthrough ── */

	it("applies custom className", () => {
		render(<Metric label="A" value={1} className="extra-class" />);
		expect(screen.getByTestId("metric-root")).toHaveClass("extra-class");
	});

	/* ── font families ── */

	it("uses font-data for value text", () => {
		render(<Metric label="A" value={42} />);
		const value = screen.getByText("42");
		expect(value.className).toContain("font-data");
	});

	it("uses font-body for label text", () => {
		render(<Metric label="Label" value={42} />);
		const label = screen.getByText("Label");
		expect(label.className).toContain("font-(--font-body)");
	});

	/* ── sub styling ── */

	it("renders sub with tertiary color for standard variant", () => {
		render(<Metric label="A" value={1} sub="info" variant="standard" />);
		const sub = screen.getByText("info");
		expect(sub.className).toContain("text-(--color-foreground-tertiary)");
	});

	it("renders sub with small font size for standard variant", () => {
		render(<Metric label="A" value={1} sub="info" variant="standard" />);
		const sub = screen.getByText("info");
		expect(sub.className).toContain("text-xs");
	});
});
