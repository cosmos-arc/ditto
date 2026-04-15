import type { ReactNode } from "react";

interface RadarLayoutProps {
	contextBar?: ReactNode;
	scopeStrip?: ReactNode;
	main: ReactNode;
	rightRail?: ReactNode;
	tabBand?: ReactNode;
	/** Optional extra class names for the root flex container */
	className?: string;
}

/**
 * RadarLayout — /markets/* scrollable pages.
 * Single-page scroll with sticky context-bar, scope-strip, and right-rail.
 * Unlike grid-locked layouts (AnalyticalLayout, CommandCenterLayout),
 * uses flex-based vertical scrolling with sticky positioning.
 * StatusBar is no longer a slot — it uses position:fixed (see status-bar.tsx).
 */
export function RadarLayout({
	contextBar,
	scopeStrip,
	main,
	rightRail,
	tabBand,
	className,
}: RadarLayoutProps) {
	const hasContextBar = Boolean(contextBar);
	const offsets = buildStickyOffsets(hasContextBar);

	return (
		<div className={`flex h-full w-full flex-col overflow-y-auto ${className ?? ""}`.trim()}>
			{contextBar && (
				<div
					className="sticky top-0 z-15 h-8 shrink-0 overflow-hidden"
					data-slot="context-bar"
				>
					{contextBar}
				</div>
			)}
			{scopeStrip && (
				<div className={`shrink-0 ${offsets.scopeStrip}`} data-slot="scope-strip">
					{scopeStrip}
				</div>
			)}
			<div className="grid grid-cols-[1fr_var(--width-radar-right-rail)]">
				<div data-slot="main">{main}</div>
				{rightRail && (
					<div
						className={`border-l border-l-(--color-border-subtle) bg-(--color-surface-1) ${offsets.rightRail}`}
						data-slot="right-rail"
					>
						{rightRail}
					</div>
				)}
			</div>
			{tabBand && <div data-slot="tab-band">{tabBand}</div>}
		</div>
	);
}

function buildStickyOffsets(hasContextBar: boolean): {
	scopeStrip: string;
	rightRail: string;
} {
	if (hasContextBar) {
		return {
			scopeStrip: "sticky top-8 z-14",
			rightRail: "sticky top-8 self-start",
		};
	}
	return {
		scopeStrip: "sticky top-0 z-14",
		rightRail: "sticky top-0 self-start",
	};
}
