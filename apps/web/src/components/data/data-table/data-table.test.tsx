import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { type ColumnDef, DataTable } from "./data-table";

/* ── Test data ── */

interface TestRow {
	readonly id: string;
	readonly name: string;
	readonly value: number;
	readonly status: string;
}

const COLUMNS: readonly ColumnDef<TestRow>[] = [
	{ id: "name", header: "名称", accessor: "name" },
	{ id: "value", header: "值", accessor: "value", align: "right", numeric: true },
	{ id: "status", header: "状态", accessor: "status" },
];

const DATA: readonly TestRow[] = [
	{ id: "a", name: "Alpha", value: 100, status: "active" },
	{ id: "b", name: "Beta", value: 200, status: "inactive" },
	{ id: "c", name: "Gamma", value: 300, status: "active" },
];

describe("DataTable", () => {
	/* ── Basic rendering ── */

	it("renders a <table> element", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		expect(document.querySelector("table")).toBeInTheDocument();
	});

	it("has data-slot='data-table' on root", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		expect(document.querySelector("[data-slot='data-table']")).toBeInTheDocument();
	});

	it("uses table-layout: fixed", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		const table = document.querySelector("table");
		expect(table?.className).toContain("table-fixed");
	});

	/* ── Header ── */

	it("renders column headers", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		expect(screen.getByText("名称")).toBeInTheDocument();
		expect(screen.getByText("值")).toBeInTheDocument();
		expect(screen.getByText("状态")).toBeInTheDocument();
	});

	it("renders thead as sticky", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		const thead = document.querySelector("thead");
		expect(thead?.className).toContain("sticky");
	});

	/* ── Data rows ── */

	it("renders a row for each data item", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		const tbody = document.querySelector("tbody");
		expect(tbody?.querySelectorAll("tr")).toHaveLength(3);
	});

	it("renders cell content from accessor key", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		expect(screen.getByText("Alpha")).toBeInTheDocument();
		expect(screen.getByText("Beta")).toBeInTheDocument();
	});

	it("renders numeric values as formatted strings", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		expect(screen.getByText("100")).toBeInTheDocument();
		expect(screen.getByText("200")).toBeInTheDocument();
	});

	/* ── Column alignment ── */

	it("right-aligns numeric columns", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		const valueHeader = screen.getByText("值");
		const th = valueHeader.closest("th");
		expect(th?.className).toContain("text-right");
	});

	it("left-aligns text columns by default", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		const nameHeader = screen.getByText("名称");
		const th = nameHeader.closest("th");
		expect(th?.className).toContain("text-left");
	});

	it("applies tabular-nums to numeric columns", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		const cells = document.querySelectorAll("td");
		const valueCell = cells[1];
		expect(valueCell?.className).toContain("tabular-nums");
	});

	/* ── Custom cell renderer ── */

	it("supports custom cell renderer via accessor function", () => {
		const columns: readonly ColumnDef<TestRow>[] = [
			{
				id: "name",
				header: "名称",
				accessor: (row) => <strong>{row.name}</strong>,
			},
		];
		render(<DataTable<TestRow> columns={columns} data={DATA} />);
		const strong = document.querySelector("strong");
		expect(strong).toBeInTheDocument();
		expect(strong?.textContent).toBe("Alpha");
	});

	/* ── Row interactions ── */

	it("calls onRowClick when a row is clicked", async () => {
		const onClick = vi.fn();
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} onRowClick={onClick} />);
		const rows = document.querySelectorAll("tbody tr");
		const firstRow = rows[0];
		expect(firstRow).toBeInstanceOf(HTMLTableRowElement);
		fireEvent.click(firstRow as HTMLTableRowElement);
		expect(onClick).toHaveBeenCalledWith(DATA[0]);
	});

	it("highlights selected row", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} selectedId="b" />);
		const rows = document.querySelectorAll("tbody tr");
		expect(rows.item(1).className).toContain("bg-(--color-surface-2)");
	});

	it("does not highlight unselected rows", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} selectedId="b" />);
		const rows = document.querySelectorAll("tbody tr");
		expect(rows.item(0).className).not.toContain("bg-(--color-surface-2)");
	});

	/* ── Empty state ── */

	it("renders empty tbody when data is empty", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={[]} />);
		const tbody = document.querySelector("tbody");
		expect(tbody?.querySelectorAll("tr")).toHaveLength(0);
	});

	/* ── Density ── */

	it("applies density attribute to table", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} density="comfortable" />);
		const table = document.querySelector("table");
		expect(table?.getAttribute("data-density")).toBe("comfortable");
	});

	it("defaults density to undefined (no attribute)", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		const table = document.querySelector("table");
		expect(table?.hasAttribute("data-density")).toBe(false);
	});

	/* ── Column width ── */

	it("applies column width via style", () => {
		const columns: readonly ColumnDef<TestRow>[] = [
			{ id: "name", header: "名称", accessor: "name", width: "200px" },
			{ id: "value", header: "值", accessor: "value" },
		];
		render(<DataTable<TestRow> columns={columns} data={DATA} />);
		const ths = document.querySelectorAll("th");
		expect(ths[0]).toHaveStyle({ width: "200px" });
	});

	/* ── className ── */

	it("merges custom className", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} className="extra-class" />);
		const wrapper = document.querySelector("[data-slot='data-table']");
		expect(wrapper?.classList.contains("extra-class")).toBe(true);
	});

	/* ── Sorting ── */

	it("sets data-sort=asc after first click on sortable column", () => {
		const columns: readonly ColumnDef<TestRow>[] = [{ id: "name", header: "名称", accessor: "name", sortable: true }];
		render(<DataTable<TestRow> columns={columns} data={DATA} />);
		const th = screen.getByText("名称").closest("th")!;
		fireEvent.click(th);
		expect(th.getAttribute("data-sort")).toBe("asc");
	});

	it("toggles sort direction on repeated clicks (asc → desc → none)", () => {
		const columns: readonly ColumnDef<TestRow>[] = [{ id: "value", header: "值", accessor: "value", sortable: true }];
		render(<DataTable<TestRow> columns={columns} data={DATA} />);
		const th = screen.getByText("值").closest("th")!;

		fireEvent.click(th);
		expect(th.getAttribute("data-sort")).toBe("asc");

		fireEvent.click(th);
		expect(th.getAttribute("data-sort")).toBe("desc");

		fireEvent.click(th);
		expect(th.getAttribute("data-sort")).toBeNull();
	});

	it("sorts numeric data ascending", () => {
		const columns: readonly ColumnDef<TestRow>[] = [
			{ id: "value", header: "值", accessor: "value", sortable: true, numeric: true },
		];
		render(<DataTable<TestRow> columns={columns} data={DATA} />);
		fireEvent.click(screen.getByText("值").closest("th")!);

		const cells = document.querySelectorAll("tbody td");
		const values = Array.from(cells).map((c) => c.textContent);
		expect(values).toEqual(["100", "200", "300"]);
	});

	it("sorts numeric data descending", () => {
		const columns: readonly ColumnDef<TestRow>[] = [
			{ id: "value", header: "值", accessor: "value", sortable: true, numeric: true },
		];
		render(<DataTable<TestRow> columns={columns} data={DATA} />);
		const th = screen.getByText("值").closest("th")!;

		fireEvent.click(th); // asc
		fireEvent.click(th); // desc

		const cells = document.querySelectorAll("tbody td");
		const values = Array.from(cells).map((c) => c.textContent);
		expect(values).toEqual(["300", "200", "100"]);
	});

	it("adds cursor-pointer to sortable column headers", () => {
		const columns: readonly ColumnDef<TestRow>[] = [{ id: "name", header: "名称", accessor: "name", sortable: true }];
		render(<DataTable<TestRow> columns={columns} data={DATA} />);
		const th = screen.getByText("名称").closest("th");
		expect(th?.className).toContain("cursor-pointer");
	});

	it("does not add cursor-pointer to non-sortable column headers", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		const th = screen.getByText("名称").closest("th");
		expect(th?.className).not.toContain("cursor-pointer");
	});

	/* ── Density padding ── */

	it("uses CSS variable padding for cells", () => {
		render(<DataTable<TestRow> columns={COLUMNS} data={DATA} />);
		const th = screen.getByText("名称").closest("th");
		expect(th?.className).toContain("px-[var(--cell-padding-x)]");
		expect(th?.className).toContain("py-[var(--cell-padding-y)]");
	});
});
