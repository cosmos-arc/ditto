import { themeQuartz } from "ag-grid-community";
import type { Theme, ThemeDefaultParams } from "ag-grid-community";

/** Ditto dark theme — maps Design Token CSS variables to AG Grid theme params. */
export const dittoTheme: Theme<ThemeDefaultParams> = themeQuartz.withParams({
	/* ── Surfaces ── */
	backgroundColor: "var(--color-surface-0)",
	foregroundColor: "var(--color-foreground)",
	chromeBackgroundColor: "var(--color-surface-1)",
	headerBackgroundColor: "var(--color-surface-2)",
	dataBackgroundColor: "var(--color-surface-0)",

	/* ── Borders ── */
	borderColor: "var(--color-border-subtle)",
	wrapperBorder: { color: "var(--color-border)", width: 1 },
	rowBorder: { color: "var(--color-border-subtle)", width: 1 },

	/* ── Text ── */
	textColor: "var(--color-foreground)",
	subtleTextColor: "var(--color-foreground-tertiary)",
	headerTextColor: "var(--color-foreground-tertiary)",
	cellTextColor: "var(--color-foreground)",

	/* ── Interaction ── */
	rowHoverColor: "var(--color-surface-3)",
	selectedRowBackgroundColor: "var(--color-surface-4)",

	/* ── Accent ── */
	accentColor: "var(--color-accent)",

	/* ── Typography ── */
	fontFamily: "var(--font-body), sans-serif",
	fontSize: "var(--text-base)",
	headerFontFamily: "var(--font-body), sans-serif",
	headerFontSize: "var(--text-sm)",
	headerFontWeight: 600,
	cellFontFamily: "var(--font-data), sans-serif",
	cellFontSize: "var(--text-sm)",

	/* ── Chrome scheme ── */
	browserColorScheme: "dark",

	/* ── Spacing ── */
	spacing: 8,
	borderRadius: 6,
	wrapperBorderRadius: 8,
});
