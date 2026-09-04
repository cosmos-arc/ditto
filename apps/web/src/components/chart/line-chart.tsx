import { Line, LineChart as RechartsLineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { cn } from "@/lib/utils";
import type { SparklinePoint } from "@/types";

type LineChartProps = {
	readonly data: readonly SparklinePoint[];
	readonly width?: number;
	readonly height?: number;
	readonly color?: string;
	readonly className?: string;
	readonly showAxes?: boolean;
	readonly showDots?: boolean;
};

export function LineChart({
	data,
	height = 200,
	color = "var(--color-brand-primary)",
	className,
	showAxes = false,
	showDots = true,
}: LineChartProps) {
	return (
		<div className={cn("w-full", className)} style={{ height }}>
			<ResponsiveContainer width="100%" height="100%">
				<RechartsLineChart data={[...data]}>
					{showAxes && (
						<>
							<XAxis
								dataKey="time"
								tick={{ fontSize: 11, fill: "var(--color-foreground-tertiary)" }}
								tickLine={false}
								axisLine={false}
							/>
							<YAxis
								tick={{ fontSize: 11, fill: "var(--color-foreground-tertiary)" }}
								tickLine={false}
								axisLine={false}
								width={45}
							/>
						</>
					)}
					<Tooltip
						contentStyle={{
							backgroundColor: "var(--color-surface-elevated)",
							border: "1px solid var(--color-border-subtle)",
							borderRadius: "6px",
							fontSize: 12,
						}}
					/>
					<Line
						type="monotone"
						dataKey="value"
						stroke={color}
						strokeWidth={1.5}
						dot={showDots ? { r: 3, fill: color } : false}
						activeDot={{ r: 4, fill: color }}
					/>
				</RechartsLineChart>
			</ResponsiveContainer>
		</div>
	);
}
