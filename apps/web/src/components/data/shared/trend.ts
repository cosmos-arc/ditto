/** Shared trend direction type and configuration for Metric and TrendCell. */

type TrendDirection = "up" | "down" | "flat";

const TREND_CONFIG: Record<TrendDirection, { symbol: string; colorClass: string }> = {
	up: { symbol: "▲", colorClass: "text-(--color-market-up)" },
	down: { symbol: "▼", colorClass: "text-(--color-market-down)" },
	flat: { symbol: "—", colorClass: "text-(--color-foreground-muted)" },
};

export { TREND_CONFIG };
export type { TrendDirection };
