import { CatalogLayout } from "@/features/shell";
import { CompareCart } from "./compare-cart";
import { ScreenerResults } from "./screener-results";
import { ScreenerToolbar } from "./screener-toolbar";

export function ScreenerPage() {
	return (
		<CatalogLayout
			toolbar={<ScreenerToolbar />}
			main={
				<div
					data-info-level="l1"
					data-info-unit="screener-main"
					className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)"
				>
					<ScreenerResults />
				</div>
			}
			detail={
				<div data-info-level="l2" data-info-unit="screener-detail">
					<CompareCart />
				</div>
			}
		/>
	);
}
