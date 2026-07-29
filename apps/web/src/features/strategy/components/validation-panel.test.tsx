import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SpecValidation } from "@/types/strategy";
import { ValidationPanel } from "./validation-panel";

const baseValidation: SpecValidation = {
	strategyId: "s",
	version: 1,
	canonicalHash: "h-candidate",
	baseSpecHash: "h-base",
	changed: true,
	valid: true,
	errors: [],
};

describe("ValidationPanel", () => {
	it("renders canonical hash and valid badge when valid", () => {
		render(<ValidationPanel validation={baseValidation} isValidating={false} />);
		expect(screen.getByText("有效")).toBeInTheDocument();
		expect(screen.getByText(/h-candidate/)).toBeInTheDocument();
		expect(screen.getByText("已变更")).toBeInTheDocument();
	});

	it("renders errors when invalid", () => {
		render(
			<ValidationPanel
				validation={{ ...baseValidation, valid: false, errors: ["bad pipeline", "missing universe"] }}
				isValidating={false}
			/>,
		);
		expect(screen.getByText("无效")).toBeInTheDocument();
		expect(screen.getByText("bad pipeline")).toBeInTheDocument();
		expect(screen.getByText("missing universe")).toBeInTheDocument();
	});

	it("shows idle prompt when no validation yet", () => {
		render(<ValidationPanel validation={null} isValidating={false} />);
		expect(screen.getByText(/编辑后点击校验/)).toBeInTheDocument();
	});

	it("shows validating state", () => {
		render(<ValidationPanel validation={null} isValidating={true} />);
		expect(screen.getByText("校验中…")).toBeInTheDocument();
	});
});
