import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";
import { TREND_CONFIG, type TrendDirection } from "../shared/trend";
import { Sparkline } from "../sparkline";

/* ── Number formatting ── */

const numberFormatter = new Intl.NumberFormat("en-US");

function formatValue(value: string | number): string {
	if (typeof value === "number") {
		return numberFormatter.format(value);
	}
	return value;
}

/* ── CVA variants ── */

const metricVariants = cva("flex", {
	variants: {
		variant: {
			standard: "flex-col gap-0.5",
			strip: "flex-row items-center gap-1.5",
			equity: "flex-col gap-1",
		},
		size: {
			sm: "",
			md: "",
			lg: "",
		},
	},
	defaultVariants: {
		variant: "standard",
		size: "md",
	},
});

/* ── Value size map ── */

const VALUE_SIZE_CLASS: Record<string, string> = {
	sm: "text-md",
	md: "text-lg",
	lg: "text-3xl",
};

/** Equity variant always uses 24px value regardless of size prop. */
const EQUITY_VALUE_CLASS = "text-3xl";

function valueSizeClass(variant: string | null | undefined, size: string | null | undefined): string {
	if (variant === "equity") return EQUITY_VALUE_CLASS;
	if (variant === "strip") return "text-sm";
	return VALUE_SIZE_CLASS[size ?? "md"];
}

function sparklineColor(trend: TrendDirection | undefined): "up" | "down" | "neutral" {
	if (trend === "up") return "up";
	if (trend === "down") return "down";
	return "neutral";
}

/* ── Props ── */

interface MetricProps
	extends React.HTMLAttributes<HTMLDivElement>,
		VariantProps<typeof metricVariants> {
	readonly label: string;
	readonly value: string | number;
	readonly sub?: string | readonly string[];
	readonly trend?: TrendDirection;
	readonly sparkline?: readonly number[];
}

/* ── Component ── */

function Metric({
	label,
	value,
	sub,
	trend,
	sparkline,
	variant = "standard",
	size = "md",
	className,
	...props
}: MetricProps) {
	const formattedValue = formatValue(value);
	const displayValue = trend ? `${TREND_CONFIG[trend].symbol} ${formattedValue}` : formattedValue;
	const valueColorClass = trend ? TREND_CONFIG[trend].colorClass : "";

	const subItems: readonly string[] = Array.isArray(sub) ? sub : sub ? [sub] : [];

	return (
		<div
			data-slot="metric"
			data-variant={variant}
			data-size={size}
			data-testid="metric-root"
			className={cn(metricVariants({ variant, size }), className)}
			{...props}
		>
			{/* Label */}
			<span
				className={cn(
					"font-(--font-body) text-sm text-(--color-foreground-tertiary)",
					variant !== "strip" && "uppercase tracking-[0.48px]",
				)}
			>
				{label}
			</span>

			{/* Value + Sparkline row */}
			<div className={cn("flex items-center gap-1.5", variant === "standard" && "flex-row")}>
				<span
					className={cn(
						"tabular-nums leading-none",
						valueSizeClass(variant, size),
						variant === "strip" ? "font-medium" : "font-semibold",
						"font-data",
						valueColorClass,
					)}
				>
					{displayValue}
				</span>
				{sparkline && sparkline.length > 0 && (
					<Sparkline
						data={sparkline}
						color={sparklineColor(trend)}
						width={48}
						height={20}
					/>
				)}
			</div>

			{/* Sub items */}
			{subItems.length > 0 && (
				<div className="flex flex-col gap-0.5">
					{subItems.map((item) => (
						<span
							key={item}
							className="text-xs text-(--color-foreground-tertiary) font-(--font-body) leading-none"
						>
							{item}
						</span>
					))}
				</div>
			)}
		</div>
	);
}

export { Metric, metricVariants };
export type { MetricProps };
