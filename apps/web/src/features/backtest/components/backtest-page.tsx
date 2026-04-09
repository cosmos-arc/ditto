import { useParams } from "@tanstack/react-router";
import { ObjectHubLayout } from "@/features/shell";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { BacktestKpiStrip } from "./backtest-kpi-strip";
import { BacktestTrades } from "./backtest-trades";
import { AreaChart } from "@/components/chart/area-chart";

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
							<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
								<div className="flex h-48 items-center justify-center text-sm text-(--color-foreground-tertiary)">
									NAV + Drawdown 双轴图 — 待图表增强
								</div>
								<BacktestTrades jobId={jobId} />
							</div>
						</TabsContent>
						<TabsContent value="returns">
							<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
								月度收益图表 — 待实现
							</div>
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
