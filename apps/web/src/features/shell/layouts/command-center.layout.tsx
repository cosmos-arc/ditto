import type { ReactNode } from "react";

interface CommandCenterLayoutProps {
	pulse?: ReactNode;
	main: ReactNode;
	sidebar?: ReactNode;
	status?: ReactNode;
}

/**
 * CommandCenterLayout — command-center pages.
 * Grid: pulse strip (full width) + main/sidebar + optional page-owned status row.
 * min-h-0 + overflow-hidden on grid-area divs ensures grid track constraints are respected.
 */
export function CommandCenterLayout({
	pulse,
	main,
	sidebar,
	status,
}: CommandCenterLayoutProps) {
	const rows = status
		? "grid-rows-[auto_1fr_var(--height-status-bar)]"
		: "grid-rows-[auto_1fr]";
	const areas = status
		? '[grid-template-areas:"pulse_pulse""main_sidebar""status_status"]'
		: '[grid-template-areas:"pulse_pulse""main_sidebar"]';

	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden",
				"grid-cols-[1fr_var(--width-sidebar)]",
				rows,
				areas,
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
			{status && <div className="[grid-area:status]" data-slot="status">{status}</div>}
		</div>
	);
}
