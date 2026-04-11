import type { ReactNode } from "react";

interface CommandCenterLayoutProps {
	pulse?: ReactNode;
	main: ReactNode;
	sidebar?: ReactNode;
	/** Optional extra class names for the root grid container */
	className?: string;
}

/**
 * CommandCenterLayout — command-center pages.
 * Grid: pulse strip (full width) + main/sidebar.
 * StatusBar is no longer a grid slot — it uses position:fixed (see status-bar.tsx).
 * min-h-0 + overflow-hidden on grid-area divs ensures grid track constraints are respected.
 */
export function CommandCenterLayout({
	pulse,
	main,
	sidebar,
	className,
}: CommandCenterLayoutProps) {
	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden",
				"grid-cols-[1fr_var(--width-sidebar)]",
				"grid-rows-[auto_1fr]",
				'[grid-template-areas:"pulse_pulse""main_sidebar"]',
				className,
			].join(" ")}
		>
			{pulse && <div className="[grid-area:pulse]" data-slot="pulse">{pulse}</div>}
			<div className="min-h-0 overflow-hidden [grid-area:main]" data-slot="main">
				{main}
			</div>
			{sidebar && (
				<div className="min-h-0 overflow-hidden [grid-area:sidebar]" data-slot="sidebar">
					{sidebar}
				</div>
			)}
		</div>
	);
}
