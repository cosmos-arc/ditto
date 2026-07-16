import { render, screen } from "@testing-library/react";
import type { ColDef } from "ag-grid-community";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { DittoGrid } from "./ditto-grid";

interface GridRow {
	readonly name: string;
	readonly value: number;
}

// AG Grid requires DOM APIs that jsdom doesn't fully support.
// We mock AgGridReact to verify the wrapper component behavior.
vi.mock("ag-grid-react", () => ({
	AgGridReact: (props: {
		readonly columnDefs?: unknown;
		readonly rowData?: unknown;
		readonly children?: ReactNode;
	}) => (
		<div
			data-testid="ag-grid-mock"
			data-column-defs={JSON.stringify(props.columnDefs)}
			data-row-data={JSON.stringify(props.rowData)}
		>
			{props.children}
		</div>
	),
}));

describe("DittoGrid", () => {
	it("renders with columnDefs and rowData", () => {
		const columnDefs: ColDef<GridRow>[] = [{ field: "name" }, { field: "value" }];
		const rowData: GridRow[] = [{ name: "Test", value: 42 }];

		render(<DittoGrid<GridRow> columnDefs={columnDefs} rowData={rowData} />);
		const grid = screen.getByTestId("ag-grid-mock");
		expect(grid).toBeInTheDocument();
	});

	it("passes columnDefs to AgGridReact", () => {
		const columnDefs: ColDef<GridRow>[] = [{ field: "name" }];
		render(<DittoGrid<GridRow> columnDefs={columnDefs} rowData={[]} />);
		const grid = screen.getByTestId("ag-grid-mock");
		const passedDefs = JSON.parse(grid.getAttribute("data-column-defs") ?? "[]") as unknown;
		expect(passedDefs).toEqual([{ field: "name" }]);
	});

	it("passes rowData to AgGridReact", () => {
		const rowData: GridRow[] = [
			{ name: "Alpha", value: 1 },
			{ name: "Beta", value: 2 },
		];
		render(<DittoGrid columnDefs={[]} rowData={rowData} />);
		const grid = screen.getByTestId("ag-grid-mock");
		const passedData = JSON.parse(grid.getAttribute("data-row-data") ?? "[]") as unknown;
		expect(passedData).toEqual([
			{ name: "Alpha", value: 1 },
			{ name: "Beta", value: 2 },
		]);
	});

	it("has data-slot attribute on wrapper", () => {
		render(<DittoGrid columnDefs={[]} rowData={[]} />);
		const wrapper = screen.getByTestId("ditto-grid-root");
		expect(wrapper).toHaveAttribute("data-slot", "ditto-grid");
	});

	it("applies ag-theme-quartz CSS class on grid container", () => {
		render(<DittoGrid columnDefs={[]} rowData={[]} />);
		const gridContainer = screen.getByTestId("ditto-grid-root").querySelector(".ag-theme-quartz");
		expect(gridContainer).toBeInTheDocument();
	});

	it("renders CSV export button", () => {
		render(<DittoGrid columnDefs={[]} rowData={[]} />);
		expect(screen.getByLabelText("Export CSV")).toBeInTheDocument();
	});
});
