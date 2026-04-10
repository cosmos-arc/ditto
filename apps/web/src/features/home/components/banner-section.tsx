import { DecisionBanner } from "@/components/domain/decision-banner";
import { useDecisionBanner } from "../hooks";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function BannerSection() {
	const { data, isLoading, refetch } = useDecisionBanner();

	if (isLoading) {
		return <LoadingSkeleton variant="panel" />;
	}

	return (
		<DittoErrorBoundary
			fallbackProps={{
				title: "决策横幅加载失败",
				onRetry: () => void refetch(),
			}}
		>
			{data && (
				<DecisionBanner
					primary={{
						label: "总权益",
						value: `¥${((data.totalEquity ?? 0) / 10000).toFixed(1)}万`,
						sub: `${data.dailyPnl >= 0 ? "+" : ""}${data.dailyPnl}`,
						trend: data.dailyPnl >= 0 ? "up" : "down",
						sparkline: data.equitySparkline,
					}}
					judgment={{
						text: data.suggestion,
						regime: {
							label: data.regimeType,
							variant: data.marketRegime === "risk_on" ? "regime-on" : "regime-off",
						},
						metrics: [
							{ label: "风控使用率", value: `${data.riskUtilization}%` },
							{ label: "杠杆率", value: `${data.leverage}x` },
							{ label: "最大回撤", value: `${data.maxDrawdown}%`, trend: "down" },
							{ label: "IVIX", value: `${data.ivix}`, trend: "down" },
						],
					}}
					actions={[
						{ label: "执行调仓", variant: "primary" },
						{ label: "查看详情", variant: "secondary" },
					]}
				/>
			)}
		</DittoErrorBoundary>
	);
}
