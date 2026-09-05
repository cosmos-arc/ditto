import { useId, useMemo } from "react";
import { cn } from "@/lib/utils";

const DEFAULT_WIDTH = 48;
const DEFAULT_HEIGHT = 20;
const DEFAULT_STROKE_WIDTH = 1.5;

export type SparklineColor = "up" | "down" | "neutral";

interface SparklineProps {
	readonly data: readonly number[];
	readonly color?: SparklineColor | undefined;
	readonly gradient?: boolean | undefined;
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

interface Point {
	readonly x: number;
	readonly y: number;
}

/** Normalize data to SVG coordinate points. */
function toPoints(data: readonly number[], width: number, height: number): Point[] {
	const len = data.length;
	if (len < 2) return [];

	const min = Math.min(...data);
	const max = Math.max(...data);
	const range = max - min || 1;

	return data.map((value, i) => ({
		x: (i / (len - 1)) * width,
		y: (1 - (value - min) / range) * height,
	}));
}

/** Build area fill path from points + bottom closure. */
function strokeLinePath(pts: readonly Point[]): string {
	if (pts.length < 2) return "";
	return pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
}

/** Build area fill path from points + bottom closure. */
function toAreaPath(pts: readonly Point[], height: number): string {
	if (pts.length < 2) return "";
	const first = pts[0];
	const last = pts.at(-1);
	if (!first || !last) return "";
	return `${strokeLinePath(pts)} L${last.x},${height} L${first.x},${height} Z`;
}

/**
 * Sparkline -- SVG mini line chart for embedding in Metric cards and grid cells.
 *
 * Renders a straight-line path from numeric data with optional gradient
 * fill and entry animation. Color maps to semantic CSS variables for market
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
	const uid = useId();
	const gradientId = `sparkline-grad-${uid}`;
	const strokeColor = COLOR_MAP[color];
	const canDraw = data.length >= 2;

	const { strokeD, areaD } = useMemo(() => {
		if (!canDraw) return { strokeD: "", areaD: "" };
		const pts = toPoints(data, width, height);
		const stroke = strokeLinePath(pts);
		const area = gradient ? toAreaPath(pts, height) : "";
		return { strokeD: stroke, areaD: area };
	}, [canDraw, data, width, height, gradient]);

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
						<stop offset="0%" stopColor={strokeColor} stopOpacity="0.2" />
						<stop offset="100%" stopColor={strokeColor} stopOpacity="0" />
					</linearGradient>
				</defs>
			)}
			{gradient && areaD && <path data-part="area" d={areaD} fill={`url(#${gradientId})`} stroke="none" />}
			{canDraw && (
				<path
					data-part="stroke"
					d={strokeD}
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
