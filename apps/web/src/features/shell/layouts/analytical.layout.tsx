import type { ReactNode } from "react";

interface AnalyticalLayoutProps {
	strip?: ReactNode;
	banner?: ReactNode;
	main: ReactNode;
	activity?: ReactNode;
	analysis?: ReactNode;
	/** Whether the activity panel is collapsed (v3 interaction framework) */
	activityCollapsed?: boolean;
	/** Let the lower analysis band use the full content width instead of stopping at the activity rail. */
	analysisSpansActivity?: boolean;
	/** Optional extra class names for the root grid container */
	className?: string;
}

/**
 * AnalyticalLayout — /markets/*, /research/*, /portfolio/*.
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
	activityCollapsed,
	analysisSpansActivity = false,
	className,
}: AnalyticalLayoutProps) {
	const hasBanner = Boolean(banner);
	const hasAnalysis = Boolean(analysis);
	const hasActivity = Boolean(activity);

	const cols = hasActivity
		? activityCollapsed
			? "grid-cols-[1fr_var(--activity-width)]"
			: "grid-cols-[1fr_var(--width-activity)]"
		: "grid-cols-[1fr]";
	const rows = buildRows(hasBanner, hasAnalysis);
	const areas = buildAreas(hasBanner, hasAnalysis, hasActivity, analysisSpansActivity);
	const narrowRows = hasActivity ? buildNarrowRows(hasBanner, hasAnalysis) : "";
	const narrowAreas = hasActivity ? buildNarrowAreas(hasBanner, hasAnalysis) : "";

	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden grid-sidebar-transition",
				cols,
				rows,
				areas,
				hasActivity && "max-md:grid-cols-[minmax(0,1fr)]",
				narrowRows,
				narrowAreas,
				className,
			]
				.filter(Boolean)
				.join(" ")}
		>
			{strip && (
				<div className="min-h-0 overflow-hidden [grid-area:strip]" data-slot="strip">
					{strip}
				</div>
			)}
			{banner && (
				<div className="overflow-hidden [grid-area:banner]" data-slot="banner">
					{banner}
				</div>
			)}
			<div className="min-h-0 overflow-hidden [grid-area:main] max-md:overflow-y-auto" data-slot="main">
				{main}
			</div>
			{activity && (
				<div
					className={[
						"min-h-0 overflow-hidden [grid-area:activity] max-md:max-h-56 max-md:overflow-y-auto",
						activityCollapsed && "w-(--width-sidebar-collapsed)",
					]
						.filter(Boolean)
						.join(" ")}
					data-slot="activity"
				>
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

function buildRows(hasBanner: boolean, hasAnalysis: boolean): string {
	if (hasBanner && hasAnalysis) {
		return "grid-rows-[minmax(var(--height-strip-min,0px),auto)_auto_minmax(var(--height-main-min,0px),1fr)_var(--height-analysis-band)]";
	}
	if (hasBanner) {
		return "grid-rows-[minmax(var(--height-strip-min,0px),auto)_auto_1fr]";
	}
	if (hasAnalysis) {
		return "grid-rows-[minmax(var(--height-strip-min,0px),auto)_minmax(var(--height-main-min,0px),1fr)_var(--height-analysis-band)]";
	}
	return "grid-rows-[minmax(var(--height-strip-min,0px),auto)_1fr]";
}

function buildAreas(
	hasBanner: boolean,
	hasAnalysis: boolean,
	hasActivity: boolean,
	analysisSpansActivity: boolean,
): string {
	if (hasActivity) {
		if (hasBanner && hasAnalysis) {
			if (analysisSpansActivity) {
				return '[grid-template-areas:"strip_strip""banner_banner""main_activity""analysis_analysis"]';
			}
			return '[grid-template-areas:"strip_strip""banner_banner""main_activity""analysis_activity"]';
		}
		if (hasBanner) {
			return '[grid-template-areas:"strip_strip""banner_banner""main_activity"]';
		}
		if (hasAnalysis) {
			if (analysisSpansActivity) {
				return '[grid-template-areas:"strip_strip""main_activity""analysis_analysis"]';
			}
			return '[grid-template-areas:"strip_strip""main_activity""analysis_activity"]';
		}
		return '[grid-template-areas:"strip_strip""main_activity"]';
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

function buildNarrowRows(hasBanner: boolean, hasAnalysis: boolean): string {
	if (hasBanner && hasAnalysis) {
		return "max-md:grid-rows-[auto_auto_minmax(0,1fr)_auto_auto]";
	}
	if (hasBanner) {
		return "max-md:grid-rows-[auto_auto_minmax(0,1fr)_auto]";
	}
	if (hasAnalysis) {
		return "max-md:grid-rows-[auto_minmax(0,1fr)_auto_auto]";
	}
	return "max-md:grid-rows-[auto_minmax(0,1fr)_auto]";
}

function buildNarrowAreas(hasBanner: boolean, hasAnalysis: boolean): string {
	if (hasBanner && hasAnalysis) {
		return 'max-md:[grid-template-areas:"strip""banner""main""activity""analysis"]';
	}
	if (hasBanner) {
		return 'max-md:[grid-template-areas:"strip""banner""main""activity"]';
	}
	if (hasAnalysis) {
		return 'max-md:[grid-template-areas:"strip""main""activity""analysis"]';
	}
	return 'max-md:[grid-template-areas:"strip""main""activity"]';
}
