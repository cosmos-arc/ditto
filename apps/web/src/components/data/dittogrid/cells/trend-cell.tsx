import { cn } from "@/lib/utils";
import { TREND_CONFIG, type TrendDirection } from "../../shared/trend";

function resolveTrend(value: number): TrendDirection {
	if (value > 0) return "up";
	if (value < 0) return "down";
	return "flat";
}

interface TrendCellProps {
	readonly value: number;
	readonly className?: string;
}

function TrendCell({ value, className }: TrendCellProps) {
	const trend = resolveTrend(value);
	const config = TREND_CONFIG[trend];

	return (
		<span
			data-slot="trend-cell"
			data-testid="trend-cell-root"
			className={cn("inline-flex items-center gap-1", config.colorClass, className)}
		>
			{config.symbol}
		</span>
	);
}

export { TrendCell };
export type { TrendCellProps };
