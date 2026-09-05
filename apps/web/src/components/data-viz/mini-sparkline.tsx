interface MiniSparklineProps {
	readonly data: readonly number[];
	readonly width?: number;
	readonly height?: number;
	readonly trend?: "up" | "down" | "neutral" | undefined;
	readonly ariaLabel?: string;
	readonly className?: string;
}

const TREND_COLORS = {
	up: "stroke-(--color-market-up)",
	down: "stroke-(--color-market-down)",
	neutral: "stroke-(--color-foreground-muted)",
} as const;

function toPoints(data: readonly number[], width: number, height: number, padding = 1): string {
	if (data.length === 0) return "";
	const min = Math.min(...data);
	const max = Math.max(...data);
	const range = max - min || 1;
	const xStep = (width - padding * 2) / (data.length - 1 || 1);
	return data
		.map((v, i) => {
			const x = padding + i * xStep;
			const y = height - padding - ((v - min) / range) * (height - padding * 2);
			return `${x},${y}`;
		})
		.join(" ");
}

function MiniSparkline({ data, width = 24, height = 12, trend = "neutral", ariaLabel, className }: MiniSparklineProps) {
	const points = toPoints(data, width, height);

	return (
		<svg
			role="img"
			aria-label={ariaLabel}
			width={width}
			height={height}
			viewBox={`0 0 ${width} ${height}`}
			fill="none"
			className={[TREND_COLORS[trend], className].filter(Boolean).join(" ")}
		>
			<polyline points={points} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
		</svg>
	);
}

export type { MiniSparklineProps };
export { MiniSparkline };
