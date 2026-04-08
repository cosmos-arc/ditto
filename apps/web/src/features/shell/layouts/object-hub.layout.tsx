import type { ReactNode } from "react";

interface ObjectHubLayoutProps {
	meta?: ReactNode;
	tabs?: ReactNode;
	main: ReactNode;
	bottom?: ReactNode;
}

/**
 * ObjectHubLayout — /instruments/:id, /strategies/:id.
 * Grid: meta + tabs + main + bottom (single column).
 */
export function ObjectHubLayout({
	meta,
	tabs,
	main,
	bottom,
}: ObjectHubLayoutProps) {
	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden",
				"grid-cols-1",
				"grid-rows-[auto_auto_1fr_auto]",
				'[grid-template-areas:"meta""tabs""main""bottom"]',
			].join(" ")}
		>
			{meta && <div className="[grid-area:meta]">{meta}</div>}
			{tabs && <div className="[grid-area:tabs]">{tabs}</div>}
			<div className="[grid-area:main]">{main}</div>
			{bottom && <div className="[grid-area:bottom]">{bottom}</div>}
		</div>
	);
}
