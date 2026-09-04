import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ParamFields } from "./param-fields";

describe("ParamFields", () => {
	it("renders numeric and string params as labelled editable fields", () => {
		render(<ParamFields params={{ k: 5, label: "momentum" }} onChange={vi.fn()} />);

		expect(screen.getByLabelText("k")).toBeInTheDocument();
		expect(screen.getByLabelText("label")).toBeInTheDocument();
	});

	it("fires onChange with the updated scalar param merged into params", () => {
		const onChange = vi.fn();
		render(<ParamFields params={{ k: 5, label: "momentum" }} onChange={onChange} />);

		fireEvent.change(screen.getByLabelText("k"), { target: { value: "10" } });

		expect(onChange).toHaveBeenLastCalledWith({ k: 10, label: "momentum" });
	});

	it("hides non-scalar params (object/array) and keeps scalars editable", () => {
		render(<ParamFields params={{ complex: { a: 1 }, k: 5 }} onChange={vi.fn()} />);

		expect(screen.queryByLabelText("complex")).not.toBeInTheDocument();
		expect(screen.getByLabelText("k")).toBeInTheDocument();
	});

	it("shows an empty hint when there are no scalar params", () => {
		render(<ParamFields params={{}} onChange={vi.fn()} />);

		expect(screen.getByText(/无可编辑参数/)).toBeInTheDocument();
	});
});
