import { useUIPreferences } from "../hooks/use-ui-preferences";
import { cn } from "@/lib/utils";

interface SidebarToggleProps {
	readonly className?: string;
}

/**
 * SidebarToggle — collapses/expands the sidebar panel.
 * Uses ChevronLeft when expanded (indicating "collapse"),
 * ChevronRight when collapsed (indicating "expand").
 */
export function SidebarToggle({ className }: SidebarToggleProps) {
	const { sidebarCollapsed, toggleSidebarCollapsed } = useUIPreferences();

	return (
		<button
			type="button"
			data-slot="sidebar-toggle"
			aria-label={sidebarCollapsed ? "展开侧边栏" : "折叠侧边栏"}
			onClick={toggleSidebarCollapsed}
			className={cn(
				"flex items-center justify-center",
				"w-full h-8 shrink-0",
				"text-(--color-foreground-muted)",
				"hover:bg-(--color-interaction-hover-subtle-bg)",
				"hover:text-(--color-foreground-secondary)",
				"transition-colors duration-150",
				"cursor-pointer",
				className,
			)}
		>
			{sidebarCollapsed ? (
				<svg className="size-4" viewBox="0 0 16 16" fill="none">
					<path
						d="M10 3L5 8L10 13"
						stroke="currentColor"
						strokeWidth="1.5"
						strokeLinecap="round"
						strokeLinejoin="round"
					/>
				</svg>
			) : (
				<svg className="size-4" viewBox="0 0 16 16" fill="none">
					<path
						d="M6 3L11 8L6 13"
						stroke="currentColor"
						strokeWidth="1.5"
						strokeLinecap="round"
						strokeLinejoin="round"
					/>
				</svg>
			)}
		</button>
	);
}
