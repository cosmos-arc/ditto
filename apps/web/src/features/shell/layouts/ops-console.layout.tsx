import type { ReactNode } from "react";

interface OpsConsoleLayoutProps {
	health?: ReactNode;
	main: ReactNode;
	detail?: ReactNode;
}

/**
 * OpsConsoleLayout — /platform/*.
 * Grid: health strip + main/detail.
 */
export function OpsConsoleLayout({
	health,
	main,
	detail,
}: OpsConsoleLayoutProps) {
	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden",
				"grid-cols-[1fr_var(--width-ops-detail)]",
				"grid-rows-[auto_1fr]",
				'[grid-template-areas:"health_health""main_detail"]',
			].join(" ")}
		>
			{health && <div className="[grid-area:health]">{health}</div>}
			<div className="[grid-area:main]">{main}</div>
			{detail && <div className="[grid-area:detail]">{detail}</div>}
		</div>
	);
}
