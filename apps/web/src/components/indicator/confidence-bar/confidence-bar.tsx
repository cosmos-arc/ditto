import { cn } from "@/lib/utils";

/* ── Types ── */

type ConfidenceColor = "brand" | "success" | "warning" | "danger" | "neutral";

interface Segment {
	readonly value: number;
	readonly color: ConfidenceColor;
	readonly label?: string;
}

/* ── Color mapping ── */

const COLOR_CLASSES: Record<ConfidenceColor, string> = {
	brand: "bg-(--color-brand-accent)",
	success: "bg-(--color-status-led-healthy)",
	warning: "bg-(--color-status-led-warning)",
	danger: "bg-(--color-status-led-critical)",
	neutral: "bg-(--color-foreground-secondary)",
};

/* ── Size mapping ── */

const SIZE_TRACK_CLASS: Record<string, string> = {
	sm: "h-1",
	md: "h-1.5",
};

/* ── Props ── */

interface ConfidenceBarProps extends React.HTMLAttributes<HTMLDivElement> {
	readonly value: number;
	readonly max?: number;
	readonly color?: ConfidenceColor;
	readonly size?: "sm" | "md";
	readonly showLabel?: boolean;
	readonly segments?: readonly Segment[];
}

/* ── Component ── */

function ConfidenceBar({
	value,
	max = 100,
	color = "neutral",
	size = "md",
	showLabel = false,
	segments,
	className,
	...props
}: ConfidenceBarProps) {
	const isSegmented = segments !== undefined && segments.length > 0;
	const percentage = Math.min((value / max) * 100, 100);

	return (
		<div
			data-slot="confidence-bar"
			data-size={size}
			data-testid="confidence-bar"
			className={cn("flex items-center gap-1.5", className)}
			{...props}
		>
			{/* Track */}
			<div
				data-slot="confidence-track"
				data-testid="confidence-track"
				className={cn("w-full overflow-hidden rounded-full bg-(--color-border-subtle)", SIZE_TRACK_CLASS[size])}
			>
				{isSegmented ? (
					/* Segmented fills */
					<div className="flex h-full">
						{segments.map((seg, i) => {
							const segPercent = Math.min((seg.value / max) * 100, 100);
							return (
								<div
									key={`seg-${i}`}
									data-testid="confidence-segment"
									className={cn("h-full rounded-full transition-[width] duration-200", COLOR_CLASSES[seg.color])}
									style={{ width: `${segPercent}%` }}
								/>
							);
						})}
					</div>
				) : (
					/* Single fill */
					<div
						data-testid="confidence-fill"
						className={cn("h-full rounded-full transition-[width] duration-200", COLOR_CLASSES[color])}
						style={{ width: `${percentage}%` }}
					/>
				)}
			</div>

			{/* Label */}
			{showLabel && (
				<span className="shrink-0 tabular-nums text-[var(--font-size-10)] text-(--color-foreground-tertiary)">
					{Math.round(percentage)}%
				</span>
			)}
		</div>
	);
}

export type { ConfidenceBarProps, ConfidenceColor, Segment };
export { ConfidenceBar };
