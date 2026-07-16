import type { ReactNode } from "react";

interface CatalogLayoutProps {
	toolbar?: ReactNode;
	main: ReactNode;
	detail?: ReactNode;
	/** Optional extra class names for the root grid container */
	className?: string;
}

/**
 * CatalogLayout — /markets/screener, /trading/signals.
 * Grid: filter toolbar + table/detail.
 */
export function CatalogLayout({ toolbar, main, detail, className }: CatalogLayoutProps) {
	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden",
				"grid-cols-[1fr_var(--width-catalog-detail)]",
				"grid-rows-[auto_1fr]",
				'[grid-template-areas:"toolbar_toolbar""main_detail"]',
				className,
			].join(" ")}
		>
			{toolbar && (
				<div className="min-h-0 overflow-hidden [grid-area:toolbar]" data-slot="toolbar">
					{toolbar}
				</div>
			)}
			<div className="min-h-0 overflow-hidden [grid-area:main]" data-slot="main">
				{main}
			</div>
			{detail && (
				<div className="min-h-0 overflow-hidden [grid-area:detail]" data-slot="detail">
					{detail}
				</div>
			)}
		</div>
	);
}
