import type { ReactNode } from "react";

interface AnalyticalLayoutProps {
	strip?: ReactNode;
	main: ReactNode;
	activity?: ReactNode;
	analysis?: ReactNode;
}

/**
 * AnalyticalLayout — /markets/*, /research/*, /trading/*.
 * Grid: scope strip + main/activity + analysis band.
 */
export function AnalyticalLayout({
	strip,
	main,
	activity,
	analysis,
}: AnalyticalLayoutProps) {
	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden",
				"grid-cols-[1fr_var(--width-activity)]",
				"grid-rows-[auto_1fr_var(--height-analysis-band)]",
				'[grid-template-areas:"strip_strip""main_activity""analysis_activity"]',
			].join(" ")}
		>
			{strip && <div className="[grid-area:strip]">{strip}</div>}
			<div className="[grid-area:main]">{main}</div>
			{activity && <div className="[grid-area:activity]">{activity}</div>}
			{analysis && <div className="[grid-area:analysis]">{analysis}</div>}
		</div>
	);
}
