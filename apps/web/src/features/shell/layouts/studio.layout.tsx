import type { CSSProperties, ReactNode } from "react";

interface StudioLayoutProps {
	/** Mode/tab switching bar above the main content (e.g. agent tabs, copilot modes) */
	modes?: ReactNode;
	source?: ReactNode;
	main: ReactNode;
	inspector?: ReactNode;
	logs?: ReactNode;
	/** Optional extra class names for the root grid container */
	className?: string;
	/** Optional inline styles — useful for overriding CSS custom properties per-page */
	style?: CSSProperties;
}

/**
 * StudioLayout — /research/strategy-studio, /ai/*.
 * Grid: optional modes bar (full width) + sources + main + inspector + optional logs.
 * When `modes` is provided, an additional row is inserted above the content columns.
 */
export function StudioLayout({
	modes,
	source,
	main,
	inspector,
	logs,
	className,
	style,
}: StudioLayoutProps) {
	const hasModes = Boolean(modes);
	const rows = hasModes
		? "grid-rows-[auto_1fr_auto]"
		: "grid-rows-[1fr_auto]";
	const areas = hasModes
		? '[grid-template-areas:"modes_modes_modes""sources_main_inspector""logs_logs_logs"]'
		: '[grid-template-areas:"sources_main_inspector""logs_logs_logs"]';

	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden",
				"grid-cols-[var(--width-studio-source)_1fr_var(--width-studio-inspector)]",
				rows,
				areas,
				className,
			].join(" ")}
			style={style}
		>
			{modes && (
				<div className="overflow-hidden [grid-area:modes]" data-slot="modes">
					{modes}
				</div>
			)}
			{source && <div className="min-h-0 overflow-hidden [grid-area:sources]" data-slot="source">{source}</div>}
			<div className="min-h-0 overflow-hidden [grid-area:main]" data-slot="main">{main}</div>
			{inspector && (
				<div className="min-h-0 overflow-hidden [grid-area:inspector]" data-slot="inspector">{inspector}</div>
			)}
			{logs && <div className="min-h-0 overflow-hidden [grid-area:logs]" data-slot="logs">{logs}</div>}
		</div>
	);
}
