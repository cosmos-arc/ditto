import { CatalogLayout } from "@/features/shell";
import { ScreenerToolbar } from "./screener-toolbar";
import { ScreenerResults } from "./screener-results";
import { CompareCart } from "./compare-cart";

export function ScreenerPage() {
	return (
		<CatalogLayout
			toolbar={<ScreenerToolbar />}
			main={
				<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
					<ScreenerResults />
				</div>
			}
			detail={<CompareCart />}
		/>
	);
}
