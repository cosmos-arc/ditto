import { DecisionBanner } from "@/components/domain/decision-banner";
import { useDecisionBanner } from "../hooks";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function BannerSection() {
	const { data, isLoading, isError, refetch } = useDecisionBanner();

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
					}}
					judgment={{
						text: data.suggestion,
						regime: {
							label: data.regimeType,
							variant: data.marketRegime === "risk_on" ? "regime-on" : "regime-off",
						},
						metrics: [
							{ label: "风控使用率", value: `${data.riskUtilization}%` },
						],
					}}
				/>
			)}
		</DittoErrorBoundary>
	);
}
