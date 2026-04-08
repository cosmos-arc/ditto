import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DittoGrid } from "./ditto-grid";

// AG Grid requires DOM APIs that jsdom doesn't fully support.
// We mock AgGridReact to verify the wrapper component behavior.
vi.mock("ag-grid-react", () => ({
	AgGridReact: (props: Record<string, unknown>) => (
		<div data-testid="ag-grid-mock" data-column-defs={JSON.stringify(props.columnDefs)} data-row-data={JSON.stringify(props.rowData)}>
			{props.children}
		</div>
	),
}));

describe("DittoGrid", () => {
	it("renders with columnDefs and rowData", () => {
		const columnDefs = [{ field: "name" }, { field: "value" }];
		const rowData = [{ name: "Test", value: 42 }];

		render(<DittoGrid columnDefs={columnDefs} rowData={rowData} />);
		const grid = screen.getByTestId("ag-grid-mock");
		expect(grid).toBeInTheDocument();
	});

	it("passes columnDefs to AgGridReact", () => {
		const columnDefs = [{ field: "symbol" }];
		render(<DittoGrid columnDefs={columnDefs} rowData={[]} />);
		const grid = screen.getByTestId("ag-grid-mock");
		const passedDefs = JSON.parse(grid.getAttribute("data-column-defs") ?? "[]");
		expect(passedDefs).toEqual([{ field: "symbol" }]);
	});

	it("passes rowData to AgGridReact", () => {
		const rowData = [{ id: 1 }, { id: 2 }];
		render(<DittoGrid columnDefs={[]} rowData={rowData} />);
		const grid = screen.getByTestId("ag-grid-mock");
		const passedData = JSON.parse(grid.getAttribute("data-row-data") ?? "[]");
		expect(passedData).toEqual([{ id: 1 }, { id: 2 }]);
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
