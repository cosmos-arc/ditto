import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
	diagnosticCategory,
	ExpressionCompileDiagnosticView,
	toExpressionDiagnostic,
} from "./expression-compile-diagnostic";

const PAYLOAD = {
	valid: false,
	diagnostics: [
		{
			code: "E021_UNKNOWN_FUNCTION",
			message: "unknown function 'cs_ranks'",
			source_line: "cs_ranks(close)",
			span: {
				start: { offset: 0, line: 1, column: 1 },
				end: { offset: 8, line: 1, column: 9 },
			},
			suggestions: ["cs_rank"],
		},
	],
};

describe("toExpressionDiagnostic", () => {
	it("extracts locator fields from the compiler payload", () => {
		const diagnostic = toExpressionDiagnostic(PAYLOAD);

		expect(diagnostic).not.toBeNull();
		expect(diagnostic?.code).toBe("E021_UNKNOWN_FUNCTION");
		expect(diagnostic?.sourceLine).toBe("cs_ranks(close)");
		expect(diagnostic?.startColumn).toBe(1);
		expect(diagnostic?.endColumn).toBe(9);
		expect(diagnostic?.suggestions).toEqual(["cs_rank"]);
	});

	it("returns null for payloads without diagnostics", () => {
		expect(toExpressionDiagnostic({ valid: true, diagnostics: [] })).toBeNull();
		expect(toExpressionDiagnostic(undefined)).toBeNull();
	});

	it("classifies field/type/usage/limit error families readably", () => {
		expect(diagnosticCategory("E021_UNKNOWN_FUNCTION")).toBe("字段/用途错误");
		expect(diagnosticCategory("E031")).toBe("类型错误");
		expect(diagnosticCategory("E011")).toBe("语法错误");
		expect(diagnosticCategory("E041_EXPRESSION_TOO_LONG")).toBe("表达式限制");
	});
});

describe("ExpressionCompileDiagnosticView", () => {
	it("renders code, position, source line with caret, and suggestions", () => {
		const diagnostic = toExpressionDiagnostic(PAYLOAD);
		if (!diagnostic) throw new Error("diagnostic missing");

		render(<ExpressionCompileDiagnosticView diagnostic={diagnostic} />);

		expect(screen.getByRole("alert")).toHaveTextContent("字段/用途错误 [E021_UNKNOWN_FUNCTION]");
		expect(screen.getByRole("alert")).toHaveTextContent("第 1 行 第 1 列");
		expect(screen.getByText("cs_ranks(close)")).toBeInTheDocument();
		expect(screen.getByTestId("expression-diagnostic-caret").textContent).toBe("^^^^^^^^");
		expect(screen.getByRole("alert")).toHaveTextContent("unknown function 'cs_ranks'");
		expect(screen.getByRole("alert")).toHaveTextContent("试试：cs_rank");
	});
});
