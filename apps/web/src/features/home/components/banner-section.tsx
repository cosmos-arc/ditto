import { DecisionBanner } from "@/components/domain/decision-banner";
import { useDecisionBanner } from "../hooks";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { Panel } from "@/features/shell/components/panel";

export function BannerSection() {
	const { data, isLoading, refetch } = useDecisionBanner();

	if (isLoading) {
		return <LoadingSkeleton variant="panel" />;
	}

	return (
		<div data-info-level="l1" data-info-unit="decision-banner">
			<DittoErrorBoundary
				fallbackProps={{
					title: "决策横幅加载失败",
					onRetry: () => void refetch(),
				}}
			>
				{data && (
					<Panel className="flex-none">
						<DecisionBanner
							className={[
								"items-center",
								"min-h-[147px]",
								"[&_[data-slot=decision-judgment]]:gap-2",
								"[&_[data-slot=decision-judgment]>div:first-child]:hidden",
								"[&_[data-slot=decision-judgment]>p]:text-sm",
								"[&_[data-slot=decision-judgment]>p]:leading-snug",
								"[&_[data-slot=decision-actions]]:flex-row",
								"[&_[data-slot=decision-actions]]:items-center",
								"[&_[data-slot=decision-actions]>span]:mb-0",
								"[&_[data-slot=decision-actions]>div]:flex-row",
								"[&_[data-slot=decision-actions]>div]:items-center",
							].join(" ")}
							primary={{
								label: "今日盈亏",
								value: `${data.dailyPnl >= 0 ? "+" : ""}¥${data.dailyPnl.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`,
								sub: `较昨日 ${data.dailyPnlPercent >= 0 ? "+" : ""}${data.dailyPnlPercent}%`,
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
									{ label: "杠杆率", value: `${data.leverage}x` },
									{ label: "回撤", value: `${data.maxDrawdown}%`, trend: "down" },
									{ label: "IVIX", value: `${data.ivix}`, trend: "down" },
									{ label: "北向资金", value: `${data.northboundFlow >= 0 ? "+" : ""}${data.northboundFlow} 亿`, trend: data.northboundFlow >= 0 ? "up" as const : "down" as const },
								],
							}}
							actions={[
								{ label: "查看信号总览", variant: "primary" as const },
								{ label: "进入研究", variant: "secondary" as const },
								{ label: "查看风控", variant: "ghost" as const },
							]}
						/>
					</Panel>
				)}
			</DittoErrorBoundary>
		</div>
	);
}
