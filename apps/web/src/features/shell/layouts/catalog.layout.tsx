import type { ReactNode } from "react";

interface CatalogLayoutProps {
	toolbar?: ReactNode;
	main: ReactNode;
	detail?: ReactNode;
}

/**
 * CatalogLayout — /markets/screener, /trading/signals.
 * Grid: filter toolbar + table/detail.
 */
export function CatalogLayout({
	toolbar,
	main,
	detail,
}: CatalogLayoutProps) {
	return (
		<div
			className={[
				"grid h-full w-full overflow-hidden",
				"grid-cols-[1fr_var(--width-catalog-detail)]",
				"grid-rows-[auto_1fr]",
				'[grid-template-areas:"toolbar_toolbar""main_detail"]',
			].join(" ")}
		>
			{toolbar && <div className="[grid-area:toolbar]">{toolbar}</div>}
			<div className="[grid-area:main]">{main}</div>
			{detail && <div className="[grid-area:detail]">{detail}</div>}
		</div>
	);
}
