import type { ReactNode } from "react";

interface CommandCenterLayoutProps {
	pulse?: ReactNode;
	main: ReactNode;
	sidebar?: ReactNode;
	/** Whether the sidebar is collapsed (v3 interaction framework) */
	sidebarCollapsed?: boolean;
	className?: string;
}

/**
 * CommandCenterLayout — command-center pages.
 * Grid: pulse strip (full width) + main/sidebar.
 * StatusBar is no longer a grid slot — it uses position:fixed (see status-bar.tsx).
 * min-h-0 + overflow-hidden on grid-area divs ensures grid track constraints are respected.
 */
export function CommandCenterLayout({ pulse, main, sidebar, sidebarCollapsed, className }: CommandCenterLayoutProps) {
	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden grid-sidebar-transition",
				"grid-cols-[1fr_var(--sidebar-width)]",
				"grid-rows-[auto_1fr]",
				'[grid-template-areas:"pulse_pulse""main_sidebar"]',
				className,
			].join(" ")}
		>
			{pulse && (
				<div className="[grid-area:pulse]" data-slot="pulse">
					{pulse}
				</div>
			)}
			<div className="min-h-0 overflow-hidden [grid-area:main]" data-slot="main">
				{main}
			</div>
			{sidebar && (
				<div
					className={[
						"min-h-0 overflow-hidden [grid-area:sidebar]",
						sidebarCollapsed && "w-(--width-sidebar-collapsed)",
					]
						.filter(Boolean)
						.join(" ")}
					data-slot="sidebar"
				>
					{sidebar}
				</div>
			)}
		</div>
	);
}
