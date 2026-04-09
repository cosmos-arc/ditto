import { cn } from "@/lib/utils";
import { Metric } from "@/components/data";
import { StatusBadge } from "@/components/status";
import type { BadgeVariant } from "@/components/status";
import { Button } from "@/components/ui/button";
import type { TrendDirection } from "@/components/data";

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

function DecisionBanner({
	primary,
	judgment,
	actions,
	className,
	...props
}: DecisionBannerProps) {
	return (
		<div
			data-slot="decision-banner"
			className={cn(
				"grid grid-cols-1 md:grid-cols-[5fr_4fr_3fr] gap-[var(--space-16)] py-[var(--space-12)] px-[var(--space-16)]",
				"border-l-2 border-l-(--color-brand-500)/35",
				className,
			)}
			{...props}
		>
			{/* Primary column */}
			<div data-slot="decision-primary" className="flex flex-col gap-[var(--space-8)]">
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
				className="flex flex-col gap-[var(--space-12)] md:border-l md:border-(--color-border-subtle) md:pl-[var(--space-16)]"
			>
				<div className="flex items-center gap-[var(--space-8)]">
					{judgment.regime && (
						<StatusBadge label={judgment.regime.label} variant={judgment.regime.variant} size="sm" />
					)}
				</div>
				<p className="text-(--font-size-14) font-semibold text-(--color-foreground-primary) leading-relaxed">
					{judgment.text}
				</p>
				{judgment.metrics.length > 0 && (
					<div className="flex flex-wrap gap-[var(--space-12)]">
						{judgment.metrics.map((metric) => (
							<div key={metric.label} className="flex flex-col gap-px">
								<span className="text-(--font-size-10) text-(--color-foreground-tertiary)">
									{metric.label}
								</span>
								<Metric
									label=""
									value={metric.value}
									trend={metric.trend}
									variant="strip"
									size="sm"
								/>
							</div>
						))}
					</div>
				)}
			</div>

			{/* Actions column */}
			{actions && actions.length > 0 && (
				<div
					data-slot="decision-actions"
					className="flex flex-col items-end gap-[var(--space-8)] md:border-l md:border-(--color-border-subtle) md:pl-[var(--space-16)]"
				>
					<div className="flex flex-col items-end gap-[var(--space-8)]">
						{actions.map((action) => (
							<Button
								key={action.label}
								variant={action.variant === "ghost" ? "ghost" : action.variant === "secondary" ? "outline" : "default"}
								size="sm"
								onClick={action.onClick}
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

export { DecisionBanner };
export type { DecisionBannerProps };
