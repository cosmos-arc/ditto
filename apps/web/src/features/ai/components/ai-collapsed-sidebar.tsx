import { SidebarToggle } from "@/features/shell/components/sidebar-toggle";
import { cn } from "@/lib/utils";

interface CollapsedItem {
	readonly icon: React.ReactNode;
	readonly badge?: number;
	readonly indicator?: "running" | "idle";
	readonly "aria-label": string;
}

interface AiCollapsedSidebarProps {
	readonly alertCount?: number;
	readonly agentStatus?: "running" | "idle";
	readonly onExpand?: () => void;
	readonly className?: string;
}

const INDICATOR_COLORS = {
	running: "bg-(--color-led-active)",
	idle: "bg-(--color-led-idle)",
} as const;

export function AiCollapsedSidebar({
	alertCount = 0,
	agentStatus = "running",
	onExpand,
	className,
}: AiCollapsedSidebarProps) {
	const items: CollapsedItem[] = [
		{
			icon: (
				<svg className="size-5" viewBox="0 0 20 20" fill="none" aria-hidden="true" focusable="false">
					<circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.5" />
					<path
						d="M10 6V10L13 12"
						stroke="currentColor"
						strokeWidth="1.5"
						strokeLinecap="round"
						strokeLinejoin="round"
					/>
				</svg>
			),
			indicator: agentStatus,
			"aria-label": "AI 状态",
		},
		{
			icon: (
				<svg className="size-5" viewBox="0 0 20 20" fill="none" aria-hidden="true" focusable="false">
					<path
						d="M3 10L7 14L13 6L17 10"
						stroke="currentColor"
						strokeWidth="1.5"
						strokeLinecap="round"
						strokeLinejoin="round"
					/>
				</svg>
			),
			"aria-label": "置信度分布",
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
			"aria-label": `AI 预警 (${alertCount})`,
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
