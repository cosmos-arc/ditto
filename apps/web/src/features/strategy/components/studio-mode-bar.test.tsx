import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { StudioModeBar } from "./studio-mode-bar";

describe("StudioModeBar", () => {
	it("renders all mode tabs", () => {
		render(
			<StudioModeBar
				modes={[
					{ id: "form", label: "Form" },
					{ id: "pipeline", label: "Pipeline" },
				]}
			/>,
		);

		expect(screen.getByRole("tab", { name: "Form" })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: "Pipeline" })).toBeInTheDocument();
		expect(screen.queryByText("Code Editor")).not.toBeInTheDocument();
	});

	it("marks first mode as active by default", () => {
		render(
			<StudioModeBar
				modes={[
					{ id: "form", label: "Form" },
					{ id: "pipeline", label: "Pipeline" },
				]}
			/>,
		);

		expect(screen.getByRole("tab", { name: "Form" })).toHaveAttribute("aria-selected", "true");
		expect(screen.getByRole("tab", { name: "Pipeline" })).toHaveAttribute("aria-selected", "false");
	});

	it("switches active mode on click", async () => {
		const user = userEvent.setup();
		render(
			<StudioModeBar
				modes={[
					{ id: "form", label: "Form" },
					{ id: "pipeline", label: "Pipeline" },
				]}
			/>,
		);

		await user.click(screen.getByRole("tab", { name: "Pipeline" }));
		expect(screen.getByRole("tab", { name: "Pipeline" })).toHaveAttribute("aria-selected", "true");
		expect(screen.getByRole("tab", { name: "Form" })).toHaveAttribute("aria-selected", "false");
	});

	it("calls onModeChange when provided", async () => {
		const user = userEvent.setup();
		const handleChange = vi.fn();
		render(
			<StudioModeBar
				modes={[
					{ id: "form", label: "Form" },
					{ id: "pipeline", label: "Pipeline" },
				]}
				onModeChange={handleChange}
			/>,
		);

		await user.click(screen.getByRole("tab", { name: "Pipeline" }));
		expect(handleChange).toHaveBeenCalledWith("pipeline");
	});

	it("renders breadcrumb navigation", () => {
		render(
			<StudioModeBar
				modes={[{ id: "form", label: "Form Builder" }]}
				breadcrumbs={["研究", "策略", "多因子动量策略 v2.3"]}
			/>,
		);

		expect(screen.getByText("研究")).toBeInTheDocument();
		expect(screen.getByText("策略")).toBeInTheDocument();
		expect(screen.getByText("多因子动量策略 v2.3")).toBeInTheDocument();
	});

	it("highlights last breadcrumb as current", () => {
		render(
			<StudioModeBar modes={[{ id: "form", label: "Form Builder" }]} breadcrumbs={["研究", "策略", "当前策略"]} />,
		);

		const current = screen.getByText("当前策略");
		expect(current).toHaveClass("text-(--color-foreground-secondary)");
	});
});
