import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { LoadingSkeleton } from "./loading-skeleton";

const DEFAULT_TABLE_COLUMNS = 4;

describe("LoadingSkeleton", () => {
	describe("shared behavior", () => {
		it("should render with data-slot and data-variant attributes", () => {
			render(<LoadingSkeleton variant="panel" />);
			const root = screen.getByTestId("loading-skeleton");
			expect(root).toHaveAttribute("data-slot", "loading-skeleton");
			expect(root).toHaveAttribute("data-variant", "panel");
		});

		it("should accept custom className", () => {
			render(<LoadingSkeleton variant="card" className="extra-class" />);
			const root = screen.getByTestId("loading-skeleton");
			expect(root).toHaveClass("extra-class");
		});
	});

	describe("variant=panel", () => {
		it("should render header shimmer with 40% width and 16px height", () => {
			render(<LoadingSkeleton variant="panel" />);
			const header = screen.getByTestId("skeleton-header");
			expect(header).toBeInTheDocument();
			expect(header.className).toContain("w-[40%]");
			expect(header.className).toContain("h-4");
		});

		it("should render default 3 text shimmer rows with 100% width and 12px height", () => {
			render(<LoadingSkeleton variant="panel" />);
			const rows = screen.getAllByTestId("skeleton-row");
			expect(rows).toHaveLength(3);
			for (const row of rows) {
				expect(row.className).toContain("w-full");
				expect(row.className).toContain("h-3");
			}
		});

		it("should render custom number of text shimmer rows", () => {
			render(<LoadingSkeleton variant="panel" rows={5} />);
			const rows = screen.getAllByTestId("skeleton-row");
			expect(rows).toHaveLength(5);
		});
	});

	describe("variant=table", () => {
		it("should render header row with equal-width columns", () => {
			render(<LoadingSkeleton variant="table" />);
			const headerRow = screen.getByTestId("skeleton-table-header");
			expect(headerRow).toBeInTheDocument();
			const headerCells = screen.getAllByTestId("skeleton-table-header-cell");
			expect(headerCells).toHaveLength(4);
			for (const cell of headerCells) {
				expect(cell.className).toContain("flex-1");
			}
		});

		it("should render data rows with equal-width columns", () => {
			render(<LoadingSkeleton variant="table" />);
			const dataRows = screen.getAllByTestId("skeleton-table-row");
			expect(dataRows).toHaveLength(3);
			for (const row of dataRows) {
				const cells = row.children;
				expect(cells.length).toBe(DEFAULT_TABLE_COLUMNS);
			}
		});

		it("should render custom columns and rows", () => {
			render(<LoadingSkeleton variant="table" columns={6} rows={5} />);
			const headerCells = screen.getAllByTestId("skeleton-table-header-cell");
			expect(headerCells).toHaveLength(6);
			const dataRows = screen.getAllByTestId("skeleton-table-row");
			expect(dataRows).toHaveLength(5);
		});
	});

	describe("variant=card", () => {
		it("should render title shimmer with 40% width", () => {
			render(<LoadingSkeleton variant="card" />);
			const title = screen.getByTestId("skeleton-card-title");
			expect(title).toBeInTheDocument();
			expect(title.className).toContain("w-[40%]");
		});

		it("should render content area shimmer block", () => {
			render(<LoadingSkeleton variant="card" />);
			const content = screen.getByTestId("skeleton-card-content");
			expect(content).toBeInTheDocument();
		});
	});

	describe("variant=metric", () => {
		it("should render label shimmer with 60% width and 10px height", () => {
			render(<LoadingSkeleton variant="metric" />);
			const label = screen.getByTestId("skeleton-metric-label");
			expect(label).toBeInTheDocument();
			expect(label.className).toContain("w-[60%]");
			expect(label.className).toContain("h-[10px]");
		});

		it("should render value shimmer with 40% width and 16px height", () => {
			render(<LoadingSkeleton variant="metric" />);
			const value = screen.getByTestId("skeleton-metric-value");
			expect(value).toBeInTheDocument();
			expect(value.className).toContain("w-[40%]");
			expect(value.className).toContain("h-4");
		});
	});

	describe("variant=chart", () => {
		it("should render large shimmer block with 160px height and full width", () => {
			render(<LoadingSkeleton variant="chart" />);
			const chart = screen.getByTestId("skeleton-chart");
			expect(chart).toBeInTheDocument();
			expect(chart.className).toContain("h-40");
			expect(chart.className).toContain("w-full");
		});
	});

	describe("shimmer styling", () => {
		it("should apply shimmer animation class to all shimmer elements", () => {
			render(<LoadingSkeleton variant="metric" />);
			const elements = screen.getAllByTestId(/^skeleton-/);
			for (const el of elements) {
				expect(el.className).toContain("animate-[skeleton-shimmer_1.5s_ease-in-out_infinite]");
			}
		});

		it("should apply shimmer gradient background", () => {
			render(<LoadingSkeleton variant="chart" />);
			const chart = screen.getByTestId("skeleton-chart");
			expect(chart.className).toContain("bg-[length:200%_100%]");
		});

		it("should apply rounded-sm for border radius on shimmer elements", () => {
			render(<LoadingSkeleton variant="metric" />);
			const elements = screen.getAllByTestId(/^skeleton-metric-/);
			for (const el of elements) {
				expect(el.className).toContain("rounded-sm");
			}
		});
	});
});
