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
			category: "SemanticError",
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

	it("uses the backend category as the single authority when present", () => {
		expect(diagnosticCategory("E021_UNKNOWN_FUNCTION", "SemanticError")).toBe("语义错误");
		expect(diagnosticCategory("E031", "TypeError")).toBe("类型错误");
		// 未知后端类别按原文透出，不再前端自造分类。
		expect(diagnosticCategory("E099", "FutureCategory")).toBe("FutureCategory");
	});

	it("falls back to the same backend mapping for legacy payloads without a category", () => {
		// E02x 统一为语义错误；不再分出不存在的 E022 分支。
		expect(diagnosticCategory("E021_UNKNOWN_FUNCTION")).toBe("语义错误");
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

		expect(screen.getByRole("alert")).toHaveTextContent("语义错误 [E021_UNKNOWN_FUNCTION]");
		expect(screen.getByRole("alert")).toHaveTextContent("第 1 行 第 1 列");
		expect(screen.getByText("cs_ranks(close)")).toBeInTheDocument();
		expect(screen.getByTestId("expression-diagnostic-caret").textContent).toBe("^^^^^^^^");
		expect(screen.getByRole("alert")).toHaveTextContent("unknown function 'cs_ranks'");
		expect(screen.getByRole("alert")).toHaveTextContent("试试：cs_rank");
	});
});
