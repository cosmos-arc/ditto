import type { TrendDirection } from "@/components/data";
import { Metric } from "@/components/data";
import type { BadgeVariant } from "@/components/status";
import { StatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* ── Types ── */

interface DecisionBannerProps extends React.HTMLAttributes<HTMLDivElement> {
	readonly primary: {
		readonly label: string;
		readonly value: string | number;
		readonly sub?: string;
		readonly trend?: TrendDirection;
		readonly sparkline?: readonly number[];
	};
	readonly judgment: {
		readonly text: string;
		readonly regime?: { readonly label: string; readonly variant: BadgeVariant };
		readonly metrics: readonly {
			readonly label: string;
			readonly value: string;
			readonly trend?: TrendDirection;
		}[];
	};
	readonly actions?: readonly {
		readonly label: string;
		readonly variant: "primary" | "secondary" | "ghost";
		readonly onClick?: () => void;
	}[];
}

/* ── Component ── */

function DecisionBanner({ primary, judgment, actions, className, ...props }: DecisionBannerProps) {
	return (
		<div
			data-slot="decision-banner"
			data-testid="decision-banner"
			className={cn(
				"grid grid-cols-1 md:grid-cols-[5fr_4fr_3fr] gap-4 py-3 px-4",
				"border-l-2 border-l-[color-mix(in_oklch,var(--color-accent)_35%,transparent)]",
				className,
			)}
			{...props}
		>
			{/* Primary column */}
			<div data-slot="decision-primary" className="flex flex-col gap-2">
				<Metric
					label={primary.label}
					value={primary.value}
					sub={primary.sub}
					trend={primary.trend}
					sparkline={primary.sparkline ? [...primary.sparkline] : undefined}
					variant="equity"
				/>
			</div>

			{/* Judgment column */}
			<div
				data-slot="decision-judgment"
				className="flex flex-col gap-3 md:border-l md:border-(--color-border-subtle) md:pl-4"
			>
				<div className="flex items-center gap-2">
					{judgment.regime && <StatusBadge label={judgment.regime.label} variant={judgment.regime.variant} size="sm" />}
				</div>
				<p className="[font-size:var(--text-md)] font-semibold text-(--color-foreground) leading-relaxed">
					{judgment.text}
				</p>
				{judgment.metrics.length > 0 && (
					<div className="flex flex-col gap-2">
						{/* Primary KPIs (first 2) */}
						{judgment.metrics.length > 0 && (
							<div className="flex gap-3">
								{judgment.metrics.slice(0, 2).map((metric) => (
									<div key={metric.label} className="flex flex-col gap-px">
										<span className="text-sm text-(--color-foreground-tertiary)">{metric.label}</span>
										<Metric label="" value={metric.value} trend={metric.trend} variant="strip" size="sm" />
									</div>
								))}
							</div>
						)}
						{/* Secondary KPIs (rest) */}
						{judgment.metrics.length > 2 && (
							<div className="flex gap-3">
								{judgment.metrics.slice(2).map((metric) => (
									<div key={metric.label} className="flex flex-col gap-px">
										<span className="text-sm text-(--color-foreground-tertiary)">{metric.label}</span>
										<Metric label="" value={metric.value} trend={metric.trend} variant="strip" size="sm" />
									</div>
								))}
							</div>
						)}
					</div>
				)}
			</div>

			{/* Actions column */}
			{actions && actions.length > 0 && (
				<div
					data-slot="decision-actions"
					className="flex flex-col items-end gap-2 md:border-l md:border-(--color-border-subtle) md:pl-4"
				>
					<span className="text-sm text-(--color-foreground-tertiary) mb-1">下一步</span>
					<div className="flex flex-col items-end gap-2">
						{actions.map((action) => (
							<Button
								key={action.label}
								variant={action.variant === "ghost" ? "ghost" : "outline"}
								size="sm"
								onClick={action.onClick}
								className={
									action.variant === "primary"
										? "border-(--color-accent) text-(--color-accent) hover:bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)]"
										: action.variant === "secondary"
											? "opacity-70"
											: undefined
								}
							>
								{action.label}
							</Button>
						))}
					</div>
				</div>
			)}
		</div>
	);
}

export type { DecisionBannerProps };
export { DecisionBanner };
