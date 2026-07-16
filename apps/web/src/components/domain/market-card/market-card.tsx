import { Sparkline } from "@/components/data";
import { StatusBadge } from "@/components/status";
import { cn } from "@/lib/utils";

/* ── Types ── */

interface MarketCardProps extends React.HTMLAttributes<HTMLElement> {
	readonly name: string;
	readonly regime: "on" | "off" | "mixed";
	readonly index: string;
	readonly change: number;
	readonly judgment: string;
	readonly sparkline?: readonly number[];
	readonly onClick?: () => void;
}

/* ── Regime → BadgeVariant mapping ── */

const REGIME_VARIANT_MAP: Record<string, "regime-on" | "regime-off" | "regime-mixed"> = {
	on: "regime-on",
	off: "regime-off",
	mixed: "regime-mixed",
};

/* ── Regime label mapping ── */

const REGIME_LABEL_MAP: Record<string, string> = {
	on: "风险偏好",
	off: "规避",
	mixed: "震荡",
};

/* ── Component ── */

function MarketCard({
	name,
	regime,
	index,
	change,
	judgment,
	sparkline,
	onClick,
	className,
	...props
}: MarketCardProps) {
	const changeStr = `${change > 0 ? "+" : ""}${change.toFixed(2)}%`;
	const content = (
		<>
			{/* Top row: name + regime */}
			<div className="flex items-center justify-between">
				<span className="text-sm font-medium text-(--color-foreground-primary)">{name}</span>
				<StatusBadge label={REGIME_LABEL_MAP[regime]} variant={REGIME_VARIANT_MAP[regime]} size="sm" />
			</div>

			{/* Index + change */}
			<div className="flex items-baseline gap-1.5">
				<span className="font-data text-[24px] font-semibold tabular-nums text-(--color-foreground-primary)">
					{index}
				</span>
				<span
					className={cn(
						"font-data text-[13px] font-semibold tabular-nums",
						change > 0 && "text-(--color-market-up)",
						change < 0 && "text-(--color-market-down)",
						change === 0 && "text-(--color-foreground-tertiary)",
					)}
				>
					{changeStr}
				</span>
			</div>

			{/* Sparkline */}
			{sparkline && sparkline.length > 1 && (
				<Sparkline data={[...sparkline]} color={change >= 0 ? "up" : "down"} width={120} height={20} />
			)}

			{/* Judgment */}
			<p className="text-sm text-(--color-foreground-tertiary) leading-normal">{judgment}</p>
		</>
	);
	const surfaceClassName = cn(
		"flex flex-col gap-2 p-3 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-2) text-left transition-colors duration-120 hover:bg-(--color-surface-3)",
		onClick && "cursor-pointer",
		className,
	);

	if (onClick) {
		return (
			<button type="button" data-slot="market-card" onClick={onClick} className={surfaceClassName} {...props}>
				{content}
			</button>
		);
	}

	return (
		<div data-slot="market-card" className={surfaceClassName} {...props}>
			{content}
		</div>
	);
}

export type { MarketCardProps };
export { MarketCard };
