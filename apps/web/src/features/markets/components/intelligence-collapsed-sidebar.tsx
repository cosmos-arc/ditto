import { SidebarToggle } from "@/features/shell/components/sidebar-toggle";
import { cn } from "@/lib/utils";

interface CollapsedItem {
	readonly icon: React.ReactNode;
	readonly badge?: number;
	readonly "aria-label": string;
}

interface IntelligenceCollapsedSidebarProps {
	readonly targetCount?: number;
	readonly activeFilterCount?: number;
	readonly onExpand?: () => void;
	readonly className?: string;
}

export function IntelligenceCollapsedSidebar({
	targetCount = 0,
	activeFilterCount = 0,
	onExpand,
	className,
}: IntelligenceCollapsedSidebarProps) {
	const items: CollapsedItem[] = [
		{
			icon: (
				<svg className="size-5" viewBox="0 0 20 20" fill="none">
					<path
						d="M10 2L10 10M10 10L7 7M10 10L13 7"
						stroke="currentColor"
						strokeWidth="1.5"
						strokeLinecap="round"
						strokeLinejoin="round"
					/>
					<circle cx="10" cy="16" r="2" stroke="currentColor" strokeWidth="1.5" />
				</svg>
			),
			"aria-label": "AI 解读",
		},
		{
			icon: (
				<svg className="size-5" viewBox="0 0 20 20" fill="none">
					<path d="M3 5H17M3 10H17M3 15H10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
				</svg>
			),
			badge: activeFilterCount > 0 ? activeFilterCount : undefined,
			"aria-label": `筛选器 (${activeFilterCount} 激活)`,
		},
		{
			icon: (
				<svg className="size-5" viewBox="0 0 20 20" fill="none">
					<circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.5" />
					<path d="M10 7V10M10 13H10.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
				</svg>
			),
			badge: targetCount > 0 ? targetCount : undefined,
			"aria-label": `关联标的 (${targetCount})`,
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
							<span className="absolute -top-0.5 -right-0.5 flex size-4 items-center justify-center rounded-full bg-(--color-accent) text-[9px] font-semibold text-white">
								{item.badge > 9 ? "9+" : item.badge}
							</span>
						)}
					</button>
				))}
			</div>
			<SidebarToggle />
		</div>
	);
}
