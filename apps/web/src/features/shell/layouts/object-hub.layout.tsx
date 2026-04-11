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
			{meta && <div className="min-h-0 overflow-hidden [grid-area:meta]" data-slot="meta">{meta}</div>}
			{tabs && <div className="min-h-0 overflow-hidden [grid-area:tabs]" data-slot="tabs">{tabs}</div>}
			<div className="min-h-0 overflow-hidden [grid-area:main]" data-slot="main">{main}</div>
			{bottom && <div className="min-h-0 overflow-hidden [grid-area:bottom]" data-slot="bottom">{bottom}</div>}
		</div>
	);
}
