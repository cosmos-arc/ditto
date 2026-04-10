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
				meta={<BacktestKpiStrip jobId={jobId} />}
				tabs={
					<TabsList>
						<TabsTrigger value="overview">概览</TabsTrigger>
						<TabsTrigger value="returns">收益</TabsTrigger>
						<TabsTrigger value="trades">交易</TabsTrigger>
					</TabsList>
				}
				main={
					<>
						<TabsContent value="overview">
							<BacktestOverview jobId={jobId} />
						</TabsContent>
						<TabsContent value="returns">
							<BacktestReturnsView jobId={jobId} />
						</TabsContent>
						<TabsContent value="trades">
							<BacktestTrades jobId={jobId} />
						</TabsContent>
					</>
				}
			/>
		</Tabs>
	);
}
