import type { ReactElement } from "react";

/** 单条编译诊断的可读呈现（编译器原始 payload → 业务可定位反馈）。 */
export type ExpressionCompileDiagnostic = {
	readonly code: string;
	/** 后端编译器的权威类别（LexError/SemanticError/...）；缺失时按代码回退。 */
	readonly category: string;
	readonly message: string;
	readonly sourceLine: string;
	readonly startLine: number;
	readonly startColumn: number;
	readonly endColumn: number;
	readonly suggestions: readonly string[];
};

/** 后端权威类别的中文呈现（键 = 后端 compile_error_category 输出）。 */
const BACKEND_CATEGORY_LABELS: Readonly<Record<string, string>> = {
	LexError: "词法错误",
	SyntaxError: "语法错误",
	SemanticError: "语义错误",
	TypeError: "类型错误",
	ComplexityError: "表达式限制",
	CompileError: "表达式错误",
};

/** 从受控表达式编译器的诊断 payload 提取可呈现字段；形状不符返回 null。 */
export function toExpressionDiagnostic(
	payload: Readonly<Record<string, unknown>> | null | undefined,
): ExpressionCompileDiagnostic | null {
	const diagnostics = payload?.["diagnostics"];
	if (!Array.isArray(diagnostics) || diagnostics.length === 0) return null;
	const first = diagnostics[0] as Readonly<Record<string, unknown>> | null;
	if (!first || typeof first !== "object") return null;
	const span = first["span"] as Readonly<Record<string, unknown>> | undefined;
	const start = span?.["start"] as Readonly<Record<string, unknown>> | undefined;
	const end = span?.["end"] as Readonly<Record<string, unknown>> | undefined;
	const code = typeof first["code"] === "string" ? first["code"] : "";
	const message = typeof first["message"] === "string" ? first["message"] : "";
	if (!code && !message) return null;
	const category = typeof first["category"] === "string" ? first["category"] : "";
	const suggestions = Array.isArray(first["suggestions"])
		? first["suggestions"].filter((item): item is string => typeof item === "string")
		: [];
	return {
		code,
		category,
		message,
		sourceLine: typeof first["source_line"] === "string" ? first["source_line"] : "",
		startLine: typeof start?.["line"] === "number" ? start["line"] : 1,
		startColumn: typeof start?.["column"] === "number" ? start["column"] : 1,
		endColumn: typeof end?.["column"] === "number" ? end["column"] : 0,
		suggestions,
	};
}

/**
 * 错误类别以后端为单一权威：payload 携带 category 时直接采用；旧载荷
 * 缺失时按错误代码回退到同一映射（E02x 统一为语义错误，不再细分出不
 * 存在的 E022 分支）。
 */
export function diagnosticCategory(code: string, backendCategory?: string): string {
	if (backendCategory) {
		return BACKEND_CATEGORY_LABELS[backendCategory] ?? backendCategory;
	}
	const fallback = BACKEND_CATEGORY_LABELS["CompileError"] ?? "表达式错误";
	if (code.startsWith("E001") || code.startsWith("E002")) return BACKEND_CATEGORY_LABELS["LexError"] ?? fallback;
	if (code.startsWith("E01")) return BACKEND_CATEGORY_LABELS["SyntaxError"] ?? fallback;
	if (code.startsWith("E02")) return BACKEND_CATEGORY_LABELS["SemanticError"] ?? fallback;
	if (code.startsWith("E03")) return BACKEND_CATEGORY_LABELS["TypeError"] ?? fallback;
	if (code.startsWith("E04")) return BACKEND_CATEGORY_LABELS["ComplexityError"] ?? fallback;
	return fallback;
}

export function ExpressionCompileDiagnosticView({
	diagnostic,
}: {
	readonly diagnostic: ExpressionCompileDiagnostic;
}): ReactElement {
	const highlightWidth = Math.max(1, diagnostic.endColumn - diagnostic.startColumn);
	return (
		<div
			className="rounded-(--radius-sm) border border-(--color-led-danger) bg-(--color-led-danger-bg) p-2"
			data-info-unit="expression-compile-diagnostic"
			role="alert"
		>
			<p className="text-[11px] font-semibold text-(--color-led-danger)">
				{diagnosticCategory(diagnostic.code, diagnostic.category)}
				{diagnostic.code ? ` [${diagnostic.code}]` : ""}
				<span className="ml-2 font-data font-normal">
					第 {diagnostic.startLine} 行 第 {diagnostic.startColumn} 列
				</span>
			</p>
			{diagnostic.sourceLine ? (
				<pre className="mt-1 overflow-x-auto font-data text-[11px] leading-4 text-(--color-foreground-secondary)">
					<code>{diagnostic.sourceLine}</code>
					<code className="block whitespace-pre text-(--color-led-danger)" data-testid="expression-diagnostic-caret">
						{" ".repeat(Math.max(0, diagnostic.startColumn - 1))}
						{"^".repeat(highlightWidth)}
					</code>
				</pre>
			) : null}
			<p className="mt-1 text-[11px] leading-4 text-(--color-foreground-secondary)">{diagnostic.message}</p>
			{diagnostic.suggestions.length > 0 ? (
				<p className="mt-1 text-[11px] text-(--color-foreground-tertiary)">试试：{diagnostic.suggestions.join("、")}</p>
			) : null}
		</div>
	);
}
