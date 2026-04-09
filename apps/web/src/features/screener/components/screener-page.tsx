import { CatalogLayout } from "@/features/shell";
import { ScreenerToolbar } from "./screener-toolbar";
import { ScreenerResults } from "./screener-results";
import { CompareCart } from "./compare-cart";

export function ScreenerPage() {
	return (
		<CatalogLayout
			toolbar={<ScreenerToolbar />}
			main={
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
					<ScreenerResults />
					<CompareCart />
				</div>
			}
		/>
	);
}
