import type { ReactNode } from "react";

interface StudioLayoutProps {
	source?: ReactNode;
	main: ReactNode;
	inspector?: ReactNode;
	logs?: ReactNode;
}

/**
 * StudioLayout — /research/strategy-studio, /ai/*.
 * Grid: sources + main + inspector + logs.
 */
export function StudioLayout({
	source,
	main,
	inspector,
	logs,
}: StudioLayoutProps) {
	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden",
				"grid-cols-[var(--width-studio-source)_1fr_var(--width-studio-inspector)]",
				"grid-rows-[auto_1fr_var(--height-status-bar)]",
				'[grid-template-areas:"sources_main_inspector""logs_logs_logs"]',
			].join(" ")}
		>
			{source && <div className="min-h-0 overflow-hidden [grid-area:sources]">{source}</div>}
			<div className="min-h-0 overflow-hidden [grid-area:main]">{main}</div>
			{inspector && (
				<div className="min-h-0 overflow-hidden [grid-area:inspector]">{inspector}</div>
			)}
			{logs && <div className="min-h-0 overflow-hidden [grid-area:logs]">{logs}</div>}
		</div>
	);
}
