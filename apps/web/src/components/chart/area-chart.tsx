import { Area, AreaChart as RechartsAreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { cn } from "@/lib/utils";
import type { SparklinePoint } from "@/types";

type AreaChartProps = {
	readonly data: readonly SparklinePoint[];
	readonly height?: number;
	readonly color?: string;
	readonly gradientId?: string;
	readonly className?: string;
	readonly showAxes?: boolean;
};

export function AreaChart({
	data,
	height = 200,
	color = "var(--color-brand-primary)",
	className,
	showAxes = false,
}: AreaChartProps) {
	const gradientId = "areaGradient";

	return (
		<div className={cn("w-full", className)} style={{ height }}>
			<svg width="0" height="0" aria-hidden="true" focusable="false" style={{ position: "absolute" }}>
				<defs>
					<linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
						<stop offset="0%" stopColor={color} stopOpacity={0.3} />
						<stop offset="100%" stopColor={color} stopOpacity={0.02} />
					</linearGradient>
				</defs>
			</svg>
			<ResponsiveContainer width="100%" height="100%">
				<RechartsAreaChart data={[...data]}>
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
					<Area type="monotone" dataKey="value" stroke={color} strokeWidth={1.5} fill={`url(#${gradientId})`} />
				</RechartsAreaChart>
			</ResponsiveContainer>
		</div>
	);
}
