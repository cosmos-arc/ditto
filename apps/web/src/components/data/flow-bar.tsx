import { cn } from "@/lib/utils";

const DEFAULT_HEIGHT = 6;

const CHART_PALETTE = [
	"var(--color-chart-1)",
	"var(--color-chart-2)",
	"var(--color-chart-3)",
	"var(--color-chart-4)",
	"var(--color-chart-5)",
	"var(--color-chart-6)",
] as const;

interface FlowBarSegment {
	readonly value: number;
	readonly label?: string;
	readonly color?: string;
}

interface FlowBarProps {
	readonly segments: readonly FlowBarSegment[];
	readonly height?: number;
	readonly trackClassName?: string;
	readonly className?: string;
}

export function FlowBar({
	segments,
	height = DEFAULT_HEIGHT,
	trackClassName,
	className,
}: FlowBarProps) {
	if (segments.length === 0) return null;

	const total = segments.reduce((sum, s) => sum + s.value, 0);
	if (total === 0) return null;

	return (
		<div data-slot="flow-bar" data-testid="flow-bar" className={className}>
			<div
				data-testid="flow-bar-track"
				className={cn(
					"rounded-full overflow-hidden",
					"bg-(--color-border-subtle)",
					trackClassName,
				)}
				style={{ height: `${height}px` }}
			>
				{segments.map((segment, index) => {
					const isLast = index === segments.length - 1;
					const pct = (segment.value / total) * 100;
					const bg = segment.color ?? CHART_PALETTE[index % CHART_PALETTE.length];

					return (
						<div
							key={`${index}-${segment.value}`}
							data-segment
							aria-label={segment.label}
							className={cn("inline-block h-full", isLast && "rounded-full")}
							style={{
								width: `${pct}%`,
								backgroundColor: bg,
							}}
						/>
					);
				})}
			</div>
		</div>
	);
}
