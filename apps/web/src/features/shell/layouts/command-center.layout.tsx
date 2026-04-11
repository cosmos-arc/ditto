import type { ReactNode } from "react";

interface CommandCenterLayoutProps {
	pulse?: ReactNode;
	main: ReactNode;
	sidebar?: ReactNode;
}

/**
 * CommandCenterLayout — Home page (/).
 * Grid: pulse strip (full width) + main/sidebar.
 * min-h-0 + overflow-hidden on grid-area divs ensures grid track constraints are respected.
 */
export function CommandCenterLayout({
	pulse,
	main,
	sidebar,
}: CommandCenterLayoutProps) {
	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden",
				"grid-cols-[1fr_var(--width-sidebar)]",
				"grid-rows-[auto_1fr]",
				'[grid-template-areas:"pulse_pulse""main_sidebar"]',
			].join(" ")}
		>
			{pulse && <div className="[grid-area:pulse]">{pulse}</div>}
			<div className="min-h-0 overflow-hidden [grid-area:main]">
				{main}
			</div>
			{sidebar && (
				<div className="min-h-0 overflow-hidden [grid-area:sidebar]">
					{sidebar}
				</div>
			)}
		</div>
	);
}
