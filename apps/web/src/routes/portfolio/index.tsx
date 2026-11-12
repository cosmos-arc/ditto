import { createFileRoute } from "@tanstack/react-router";
import { fetchInstrumentIdentity } from "@/features/instruments";
import { PortfolioPage } from "@/features/portfolio";

function PortfolioOverviewRoute() {
	return (
		<PortfolioPage
			mode="comparison"
			resolveInstrument={async (instrumentId) => {
				try {
					return await fetchInstrumentIdentity(String(instrumentId));
				} catch {
					// 未知或暂不可读的对象保留内部 ID 回退，不阻断复盘。
					return null;
				}
			}}
		/>
	);
}

export const Route = createFileRoute("/portfolio/")({
	component: PortfolioOverviewRoute,
	staticData: { title: "Portfolio Overview" },
});
