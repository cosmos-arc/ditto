import { Sparkline, type SparklineColor } from "@/components/data/sparkline";

interface SparklineCellProps {
	readonly data: readonly number[];
	readonly color?: SparklineColor;
	readonly gradient?: boolean;
	readonly className?: string;
}

function SparklineCell({ data, color, gradient, className }: SparklineCellProps) {
	return (
		<span data-slot="sparkline-cell" data-testid="sparkline-cell-root" className={className}>
			<Sparkline data={data} color={color} gradient={gradient} />
		</span>
	);
}

export type { SparklineCellProps };
export { SparklineCell };
