import { CatalogLayout } from "@/features/shell";
import { SignalsList } from "./signals-list";

export function SignalsPage() {
	return (
		<CatalogLayout
			main={
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
					<SignalsList />
				</div>
			}
		/>
	);
}
