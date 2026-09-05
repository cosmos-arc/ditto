import { MiniSparkline } from "@/components/data-viz";
import { SidebarToggle } from "@/features/shell";
import { cn } from "@/lib/utils";

interface CollapsedItem {
	readonly icon: React.ReactNode;
	readonly badge?: number | undefined;
	readonly indicator?: "healthy" | "degraded" | "warning" | "critical";
	readonly "aria-label": string;
}

interface HomeCollapsedSidebarProps {
	readonly alertCount?: number;
	readonly healthStatus?: "healthy" | "degraded" | "warning" | "critical";
	readonly marketTrendData?: readonly number[];
	readonly onExpand?: () => void;
	readonly className?: string;
}

const INDICATOR_COLORS = {
	healthy: "bg-(--color-status-led-healthy)",
	degraded: "bg-(--color-status-led-degraded)",
	warning: "bg-(--color-status-led-warning)",
	critical: "bg-(--color-status-led-critical)",
} as const;

export function HomeCollapsedSidebar({
	alertCount = 0,
	healthStatus = "healthy",
	marketTrendData,
	onExpand,
	className,
}: HomeCollapsedSidebarProps) {
	const firstMarketValue = marketTrendData?.[0];
	const lastMarketValue = marketTrendData?.at(-1);
	const marketTrend =
		firstMarketValue !== undefined && lastMarketValue !== undefined
			? lastMarketValue >= firstMarketValue
				? "up"
				: "down"
			: undefined;

	const items: CollapsedItem[] = [
		{
			icon: marketTrendData ? (
				<MiniSparkline data={marketTrendData} trend={marketTrend} ariaLabel="市场脉搏趋势" />
			) : (
				<svg className="size-5" viewBox="0 0 20 20" fill="none" aria-hidden="true" focusable="false">
					<path
						d="M2 14L6 10L10 13L14 6L18 8"
						stroke="currentColor"
						strokeWidth="1.5"
						strokeLinecap="round"
						strokeLinejoin="round"
					/>
				</svg>
			),
			"aria-label": "市场脉搏",
		},
		{
			icon: (
				<svg className="size-5" viewBox="0 0 20 20" fill="none" aria-hidden="true" focusable="false">
					<path
						d="M10 3L10 10M10 10L7 7M10 10L13 7"
						stroke="currentColor"
						strokeWidth="1.5"
						strokeLinecap="round"
						strokeLinejoin="round"
					/>
					<path d="M3 17H17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
				</svg>
			),
			badge: alertCount > 0 ? alertCount : undefined,
			"aria-label": `全局预警 (${alertCount})`,
		},
		{
			icon: (
				<svg className="size-5" viewBox="0 0 20 20" fill="none" aria-hidden="true" focusable="false">
					<path
						d="M10 3C5.58 3 2 6.58 2 11H10V3Z"
						stroke="currentColor"
						strokeWidth="1.5"
						strokeLinecap="round"
						strokeLinejoin="round"
					/>
					<path
						d="M10 3C14.42 3 18 6.58 18 11H10V3Z"
						stroke="currentColor"
						strokeWidth="1.5"
						strokeLinecap="round"
						strokeLinejoin="round"
					/>
					<rect x="2" y="13" width="16" height="4" rx="1" stroke="currentColor" strokeWidth="1.5" />
				</svg>
			),
			indicator: healthStatus,
			"aria-label": `数据健康 (${healthStatus})`,
		},
	];

	return (
		<div
			data-slot="sidebar-collapsed"
			className={cn(
				"flex h-full w-(--width-sidebar-collapsed) flex-col items-center",
				"border-l border-(--color-border-subtle)",
				"bg-(--color-surface-1)",
				className,
			)}
		>
			<div className="flex flex-1 flex-col items-center gap-2 py-3">
				{items.map((item) => (
					<button
						key={item["aria-label"]}
						type="button"
						aria-label={item["aria-label"]}
						onClick={onExpand}
						className={cn(
							"relative flex size-10 items-center justify-center",
							"rounded-[var(--radius-sm)]",
							"text-(--color-foreground-secondary)",
							"hover:bg-(--color-interaction-hover-subtle-bg)",
							"hover:text-(--color-foreground)",
							"transition-colors duration-150",
							"cursor-pointer",
						)}
					>
						{item.icon}
						{item.badge !== undefined && (
							<span className="absolute -top-0.5 -right-0.5 flex size-4 items-center justify-center rounded-full bg-(--color-risk-critical) text-[9px] font-semibold text-white">
								{item.badge > 9 ? "9+" : item.badge}
							</span>
						)}
						{item.indicator && (
							<span
								className={cn("absolute bottom-0.5 right-0.5 size-2 rounded-full", INDICATOR_COLORS[item.indicator])}
							/>
						)}
					</button>
				))}
			</div>
			<SidebarToggle />
		</div>
	);
}
