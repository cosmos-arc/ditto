import { useId, useMemo } from "react";
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

interface Point {
	readonly x: number;
	readonly y: number;
}

/** Normalize data to SVG coordinate points. */
function toPoints(
	data: readonly number[],
	width: number,
	height: number,
): Point[] {
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

/** Convert points to SVG path using Catmull-Rom to cubic Bezier interpolation. */
function catmullRomPath(pts: readonly Point[]): string {
	if (pts.length < 2) return "";
	if (pts.length === 2) {
		return `M${pts[0].x},${pts[0].y} L${pts[1].x},${pts[1].y}`;
	}

	let d = `M${pts[0].x},${pts[0].y}`;

	for (let i = 0; i < pts.length - 1; i++) {
		const p0 = pts[Math.max(0, i - 1)];
		const p1 = pts[i];
		const p2 = pts[i + 1];
		const p3 = pts[Math.min(pts.length - 1, i + 2)];

		const cp1x = p1.x + (p2.x - p0.x) / 6;
		const cp1y = p1.y + (p2.y - p0.y) / 6;
		const cp2x = p2.x - (p3.x - p1.x) / 6;
		const cp2y = p2.y - (p3.y - p1.y) / 6;

		d += ` C${cp1x},${cp1y} ${cp2x},${cp2y} ${p2.x},${p2.y}`;
	}

	return d;
}

/** Build area fill path from pre-computed stroke path + bottom closure. */
function toAreaPath(strokeD: string, pts: readonly Point[], height: number): string {
	if (!strokeD || pts.length < 2) return "";
	return `${strokeD} L${pts[pts.length - 1].x},${height} L${pts[0].x},${height} Z`;
}

/**
 * Sparkline -- SVG mini line chart for embedding in Metric cards and grid cells.
 *
 * Renders a Catmull-Rom smoothed path from numeric data with optional gradient
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
		const stroke = catmullRomPath(pts);
		const area = gradient ? toAreaPath(stroke, pts, height) : "";
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
						<stop offset="0%" stopColor={strokeColor} stopOpacity="0.3" />
						<stop offset="100%" stopColor={strokeColor} stopOpacity="0" />
					</linearGradient>
				</defs>
			)}
			{gradient && areaD && (
				<path
					data-part="area"
					d={areaD}
					fill={`url(#${gradientId})`}
					stroke="none"
				/>
			)}
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
