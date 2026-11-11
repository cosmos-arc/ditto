import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { StrategyAuthorOperation, StrategyAuthorPreview } from "@/types/strategy";
import { StrategyAuthorPreviewSheet } from "./strategy-author-preview-sheet";

function operation(
	subjectId: string,
	valid: boolean,
	payload: Readonly<Record<string, unknown>>,
): StrategyAuthorOperation {
	return {
		kind: "compile",
		subjectId,
		subjectVersion: "1",
		valid,
		changed: false,
		publishable: false,
		payloadHash: "a".repeat(8),
		payload,
		lineage: [],
	};
}

function preview(compile: readonly StrategyAuthorOperation[]): StrategyAuthorPreview {
	const valid = compile.every((item) => item.valid);
	return {
		strategyId: "s",
		baseVersion: 1,
		valid,
		publishable: false,
		canonicalHash: valid ? "b".repeat(64) : null,
		draft: operation("s@draft", true, {}),
		compile,
		validation: operation("s@validate", valid, {}),
		diff: operation("s@diff", true, {}),
		tests: [
			{ name: "draft_valid", passed: true, detail: "" },
			{ name: "expressions_compile", passed: valid, detail: "" },
		],
	};
}

describe("StrategyAuthorPreviewSheet readable compile diagnostics", () => {
	it("shows the failing expression text with locator diagnostics, not just PASS/FAIL", () => {
		render(
			<StrategyAuthorPreviewSheet
				open
				onClose={() => {}}
				preview={preview([
					operation("author_expression_1", true, {}),
					operation("author_expression_2", false, {
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
					}),
				])}
				expressions={["momentum_1m", "cs_ranks(close)"]}
				isPending={false}
				isStale={false}
				error={null}
			/>,
		);

		// 编译卡按行号命名并展示表达式文本：错误定位到具体表达式。
		expect(screen.getByText("表达式 2")).toBeInTheDocument();
		expect(screen.getAllByText("cs_ranks(close)").length).toBeGreaterThanOrEqual(2);
		// 诊断可读：类别+代码、位置、源行、修复建议。
		const alert = screen.getByRole("alert");
		expect(alert).toHaveTextContent("字段/用途错误 [E021_UNKNOWN_FUNCTION]");
		expect(alert).toHaveTextContent("第 1 行 第 1 列");
		expect(alert).toHaveTextContent("unknown function 'cs_ranks'");
		expect(alert).toHaveTextContent("试试：cs_rank");
		expect(screen.getByTestId("expression-diagnostic-caret").textContent).toBe("^^^^^^^^");
	});

	it("keeps passing rows compact without diagnostics blocks", () => {
		render(
			<StrategyAuthorPreviewSheet
				open
				onClose={() => {}}
				preview={preview([operation("author_expression_1", true, { valid: true })])}
				expressions={["momentum_1m"]}
				isPending={false}
				isStale={false}
				error={null}
			/>,
		);

		expect(screen.getByText("表达式 1")).toBeInTheDocument();
		expect(screen.queryByRole("alert")).toBeNull();
	});
});
