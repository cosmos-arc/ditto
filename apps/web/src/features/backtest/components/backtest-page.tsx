import { useParams } from "@tanstack/react-router";
import { ObjectHubLayout } from "@/features/shell";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { BacktestKpiStrip } from "./backtest-kpi-strip";
import { BacktestTrades } from "./backtest-trades";
import { BacktestOverview } from "./backtest-overview";
import { BacktestReturnsView } from "./backtest-returns-view";

export function BacktestPage() {
	const { id } = useParams({ strict: false }) as { id: string };
	const jobId = id ?? "";

	return (
		<Tabs defaultValue="overview">
			<ObjectHubLayout
				meta={
					<div data-info-level="l1" data-info-unit="backtest-kpi-strip">
						<BacktestKpiStrip jobId={jobId} />
					</div>
				}
				tabs={
					<div data-info-level="l1" data-info-unit="backtest-tabs">
						<TabsList>
							<TabsTrigger value="overview">概览</TabsTrigger>
							<TabsTrigger value="returns">收益</TabsTrigger>
							<TabsTrigger value="trades">交易</TabsTrigger>
						</TabsList>
					</div>
				}
				main={
					<>
						<TabsContent value="overview">
							<div data-info-level="l1" data-info-unit="backtest-overview">
								<BacktestOverview jobId={jobId} />
							</div>
						</TabsContent>
						<TabsContent value="returns">
							<div data-info-level="l1" data-info-unit="backtest-returns">
								<BacktestReturnsView jobId={jobId} />
							</div>
						</TabsContent>
						<TabsContent value="trades">
							<div data-info-level="l1" data-info-unit="backtest-trades">
								<BacktestTrades jobId={jobId} />
							</div>
						</TabsContent>
					</>
				}
			/>
		</Tabs>
	);
}
