import type { ReactNode } from "react";

interface OpsConsoleLayoutProps {
	health?: ReactNode;
	main: ReactNode;
	detail?: ReactNode;
	/** Optional extra class names for the root grid container */
	className?: string;
}

/**
 * OpsConsoleLayout — /platform/*.
 * Grid: health strip + main/detail.
 * When detail is not provided, main takes full width (single-column grid).
 */
export function OpsConsoleLayout({
	health,
	main,
	detail,
	className,
}: OpsConsoleLayoutProps) {
	const hasDetail = Boolean(detail);

	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden",
				hasDetail
					? "grid-cols-[1fr_var(--width-ops-detail)]"
					: "grid-cols-[1fr]",
				"grid-rows-[auto_1fr]",
				hasDetail
					? '[grid-template-areas:"health_health""main_detail"]'
					: '[grid-template-areas:"health""main"]',
				className,
			].join(" ")}
		>
			{health && <div className="min-h-0 overflow-hidden [grid-area:health]" data-slot="health">{health}</div>}
			<div className="min-h-0 overflow-hidden [grid-area:main]" data-slot="main">{main}</div>
			{detail && <div className="min-h-0 overflow-hidden [grid-area:detail]" data-slot="detail">{detail}</div>}
		</div>
	);
}
