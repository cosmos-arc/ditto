import { cn } from "@/lib/utils";

const DEFAULT_SIZE = 64;
const STROKE_RATIO = 0.12;

interface DonutGaugeProps {
	readonly value: number;
	readonly label?: string;
	readonly size?: number;
	readonly color?: string;
	readonly className?: string;
}

/**
 * DonutGauge -- SVG ring progress indicator.
 *
 * Renders a track circle (background) and value circle (foreground) using
 * stroke-dasharray / stroke-dashoffset for smooth progress. Optionally shows
 * percentage text in the center when a label is provided.
 */
export function DonutGauge({
	value,
	label,
	size = DEFAULT_SIZE,
	color = "var(--color-accent)",
	className,
}: DonutGaugeProps) {
	const clamped = Math.min(Math.max(value, 0), 1);
	const strokeWidth = size * STROKE_RATIO;
	const radius = (size - strokeWidth) / 2;
	const circumference = 2 * Math.PI * radius;
	const dashoffset = circumference * (1 - clamped);
	const center = size / 2;
	const percentage = Math.round(clamped * 100);
	const ariaLabel = label ? `${label} ${percentage}%` : `${percentage}%`;

	return (
		<svg
			data-slot="donut-gauge"
			width={size}
			height={size}
			viewBox={`0 0 ${size} ${size}`}
			role="img"
			aria-label={ariaLabel}
			className={cn("overflow-visible", className)}
		>
			{/* Track */}
			<circle
				cx={center}
				cy={center}
				r={radius}
				fill="none"
				stroke="var(--color-border)"
				strokeWidth={strokeWidth}
			/>
			{/* Value */}
			<circle
				cx={center}
				cy={center}
				r={radius}
				fill="none"
				stroke={color}
				strokeWidth={strokeWidth}
				strokeLinecap="round"
				strokeDasharray={circumference}
				strokeDashoffset={dashoffset}
				transform={`rotate(-90 ${center} ${center})`}
			/>
			{/* Center text */}
			{label && (
				<text
					x={center}
					y={center}
					textAnchor="middle"
					dominantBaseline="central"
					className={cn("font-data tabular-nums fill-[var(--color-foreground)]")}
					fontSize={size * 0.2}
				>
					{`${percentage}%`}
				</text>
			)}
		</svg>
	);
}
