import type { ReactNode } from "react";

interface AnalyticalLayoutProps {
	strip?: ReactNode;
	banner?: ReactNode;
	main: ReactNode;
	activity?: ReactNode;
	analysis?: ReactNode;
}

/**
 * AnalyticalLayout — /markets/*, /research/*, /trading/*.
 * Grid: scope strip + optional banner + main/activity + optional analysis band.
 * When `banner` is provided, an additional full-width row is inserted between strip and main.
 */
export function AnalyticalLayout({
	strip,
	banner,
	main,
	activity,
	analysis,
}: AnalyticalLayoutProps) {
	const hasBanner = Boolean(banner);
	const hasAnalysis = Boolean(analysis);

	const rows = buildRows(hasBanner, hasAnalysis);
	const areas = buildAreas(hasBanner, hasAnalysis);

	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden",
				"grid-cols-[1fr_var(--width-activity)]",
				rows,
				areas,
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

function buildRows(hasBanner: boolean, hasAnalysis: boolean): string {
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

function buildAreas(hasBanner: boolean, hasAnalysis: boolean): string {
	if (hasBanner && hasAnalysis) {
		return '[grid-template-areas:"strip_strip""banner_banner""main_activity""analysis_activity"]';
	}
	if (hasBanner) {
		return '[grid-template-areas:"strip_strip""banner_banner""main_activity"]';
	}
	if (hasAnalysis) {
		return '[grid-template-areas:"strip_strip""main_activity""analysis_activity"]';
	}
	return '[grid-template-areas:"strip_strip""main_activity"]';
}
