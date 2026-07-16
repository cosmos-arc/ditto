import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataToolbar } from "./data-toolbar";

describe("DataToolbar", () => {
	it("marks table actions with data toolbar semantics", () => {
		render(
			<DataToolbar
				searchLabel="搜索标的"
				selectedCount={3}
				onSearch={() => undefined}
				onFilter={() => undefined}
				onColumns={() => undefined}
				onExport={() => undefined}
			/>,
		);

		expect(screen.getByRole("toolbar", { name: "数据表工具栏" })).toHaveAttribute(
			"data-table-toolbar",
			"root",
		);
		expect(screen.getByRole("button", { name: "搜索标的" })).toHaveAttribute(
			"data-table-toolbar",
			"search",
		);
		expect(screen.getByRole("button", { name: "筛选" })).toHaveAttribute(
			"data-table-toolbar",
			"filter",
		);
		expect(screen.getByRole("button", { name: "列配置" })).toHaveAttribute(
			"data-table-toolbar",
			"columns",
		);
		expect(screen.getByRole("button", { name: "导出" })).toHaveAttribute(
			"data-table-toolbar",
			"export",
		);
		expect(screen.getByText("已选 3 项")).toBeInTheDocument();
	});

	it("renders bulk state only when rows are selected", () => {
		const { rerender } = render(<DataToolbar selectedCount={0} />);

		expect(screen.queryByText(/已选/)).not.toBeInTheDocument();

		rerender(<DataToolbar selectedCount={2} />);

		expect(screen.getByText("已选 2 项")).toBeInTheDocument();
	});

	it("does not expose local table actions as shell utilities", () => {
		const { container } = render(
			<DataToolbar
				onSearch={() => undefined}
				onFilter={() => undefined}
				onColumns={() => undefined}
				onExport={() => undefined}
			/>,
		);

		expect(container.querySelector("[data-shell-utility]")).not.toBeInTheDocument();
	});
});
