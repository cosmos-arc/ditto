import type { ReactNode } from "react";

interface AnalyticalLayoutProps {
	strip?: ReactNode;
	banner?: ReactNode;
	main: ReactNode;
	activity?: ReactNode;
	analysis?: ReactNode;
	/** Optional extra class names for the root grid container */
	className?: string;
}

/**
 * AnalyticalLayout — /markets/*, /research/*, /trading/*.
 * Grid: scope strip + optional banner + main (+ optional activity rail) + optional analysis band.
 *
 * Two modes:
 * - **With activity**: 2-column grid (1fr + --width-activity)
 * - **Without activity**: single-column full-width
 */
export function AnalyticalLayout({
	strip,
	banner,
	main,
	activity,
	analysis,
	className,
}: AnalyticalLayoutProps) {
	const hasBanner = Boolean(banner);
	const hasAnalysis = Boolean(analysis);
	const hasActivity = Boolean(activity);

	const cols = hasActivity ? "grid-cols-[1fr_var(--width-activity)]" : "grid-cols-[1fr]";
	const rows = buildRows(hasBanner, hasAnalysis, hasActivity);
	const areas = buildAreas(hasBanner, hasAnalysis, hasActivity);

	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden",
				cols,
				rows,
				areas,
				className,
			].join(" ")}
		>
			{strip && (
				<div className="min-h-0 overflow-hidden [grid-area:strip]" data-slot="strip">
					{strip}
				</div>
			)}
			{banner && (
				<div className="overflow-hidden [grid-area:banner]" data-slot="banner">{banner}</div>
			)}
			<div className="min-h-0 overflow-hidden [grid-area:main]" data-slot="main">{main}</div>
			{activity && (
				<div className="min-h-0 overflow-hidden [grid-area:activity]" data-slot="activity">
					{activity}
				</div>
			)}
			{analysis && (
				<div className="min-h-0 overflow-hidden [grid-area:analysis]" data-slot="analysis">
					{analysis}
				</div>
			)}
		</div>
	);
}

function buildRows(hasBanner: boolean, hasAnalysis: boolean, hasActivity: boolean): string {
	if (hasBanner && hasAnalysis) {
		return "grid-rows-[auto_auto_1fr_var(--height-analysis-band)]";
	}
	if (hasBanner) {
		return "grid-rows-[auto_auto_1fr]";
	}
	if (hasAnalysis) {
		return "grid-rows-[auto_1fr_var(--height-analysis-band)]";
	}
	return "grid-rows-[auto_1fr]";
}

function buildAreas(hasBanner: boolean, hasAnalysis: boolean, hasActivity: boolean): string {
	if (hasActivity) {
		const m = "main_activity";
		const a = "analysis_activity";
		if (hasBanner && hasAnalysis) {
			return `[grid-template-areas:"strip_strip""banner_banner""${m}""${a}"]`;
		}
		if (hasBanner) {
			return `[grid-template-areas:"strip_strip""banner_banner""${m}"]`;
		}
		if (hasAnalysis) {
			return `[grid-template-areas:"strip_strip""${m}""${a}"]`;
		}
		return `[grid-template-areas:"strip_strip""${m}"]`;
	}
	// Single-column: all areas span full width
	if (hasBanner && hasAnalysis) {
		return '[grid-template-areas:"strip""banner""main""analysis"]';
	}
	if (hasBanner) {
		return '[grid-template-areas:"strip""banner""main"]';
	}
	if (hasAnalysis) {
		return '[grid-template-areas:"strip""main""analysis"]';
	}
	return '[grid-template-areas:"strip""main"]';
}
