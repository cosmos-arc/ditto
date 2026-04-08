import { cn } from "@/lib/utils";

const DEFAULT_WIDTH = 48;
const DEFAULT_HEIGHT = 20;
const DEFAULT_STROKE_WIDTH = 1.5;

export type SparklineColor = "up" | "down" | "neutral";

interface SparklineProps {
	readonly data: readonly number[];
	readonly color?: SparklineColor;
	readonly gradient?: boolean;
	readonly strokeWidth?: number;
	readonly animate?: boolean;
	readonly width?: number;
	readonly height?: number;
	readonly className?: string;
}

const COLOR_MAP: Record<SparklineColor, string> = {
	up: "var(--color-market-up)",
	down: "var(--color-market-down)",
	neutral: "var(--color-foreground-muted)",
};

/** Convert data values to SVG polyline points string. */
function toPoints(
	data: readonly number[],
	width: number,
	height: number,
): string {
	const len = data.length;
	if (len < 2) return "";

	const min = Math.min(...data);
	const max = Math.max(...data);
	const range = max - min || 1;

	return data
		.map((value, i) => {
			const x = (i / (len - 1)) * width;
			const y = (1 - (value - min) / range) * height;
			return `${x},${y}`;
		})
		.join(" ");
}

/** Build polygon points for gradient fill: polyline points + bottom-right + bottom-left corners. */
function toPolygonPoints(points: string, height: number): string {
	if (!points) return "";
	const firstX = points.slice(0, points.indexOf(","));
	const lastX = points.slice(points.lastIndexOf(",") + 1);
	return `${points} ${lastX},${height} ${firstX},${height}`;
}

/**
 * Sparkline -- SVG mini line chart for embedding in Metric cards and grid cells.
 *
 * Renders a normalized polyline from numeric data with optional gradient fill
 * and entry animation. Color maps to semantic CSS variables for market
 * up/down/neutral states.
 */
export function Sparkline({
	data,
	color = "neutral",
	gradient = false,
	strokeWidth = DEFAULT_STROKE_WIDTH,
	animate = false,
	width = DEFAULT_WIDTH,
	height = DEFAULT_HEIGHT,
	className,
}: SparklineProps) {
	const strokeColor = COLOR_MAP[color];
	const canDraw = data.length >= 2;

	const points = canDraw ? toPoints(data, width, height) : "";
	const polygonPoints = canDraw ? toPolygonPoints(points, height) : "";
	const gradientId = "sparkline-gradient";

	return (
		<svg
			data-slot="sparkline"
			data-variant={color}
			width={width}
			height={height}
			viewBox={`0 0 ${width} ${height}`}
			className={cn("overflow-visible", className)}
			role="img"
			aria-hidden="true"
			fill="none"
		>
			{gradient && canDraw && (
				<defs>
					<linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
						<stop offset="0%" stopColor={strokeColor} stopOpacity="0.3" />
						<stop offset="100%" stopColor={strokeColor} stopOpacity="0" />
					</linearGradient>
				</defs>
			)}
			{gradient && canDraw && (
				<polygon
					points={polygonPoints}
					fill={`url(#${gradientId})`}
					stroke="none"
				/>
			)}
			{canDraw && (
				<polyline
					points={points}
					fill="none"
					stroke={strokeColor}
					strokeWidth={strokeWidth}
					strokeLinecap="round"
					strokeLinejoin="round"
					className={animate ? "animate-sparkline" : undefined}
				/>
			)}
		</svg>
	);
}
