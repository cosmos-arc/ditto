import { AnalyticalLayout } from "@/features/shell";
import { ASharesOverview } from "./a-shares-overview";

export function ASharesPage() {
	return (
		<AnalyticalLayout
			main={
				<div className="p-[var(--density-panel-padding)] overflow-y-auto h-full">
					<ASharesOverview />
				</div>
			}
		/>
	);
}
