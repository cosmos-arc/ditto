import { useSignalDetail } from "../hooks/use-signal-detail";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

type RiskCheckStatus = "pass" | "warn" | "fail";

const STATUS_STYLE: Record<RiskCheckStatus, string> = {
	pass: "text-(--color-led-success)",
	warn: "text-(--color-led-warning)",
	fail: "text-(--color-led-error)",
};

const STATUS_ICON: Record<RiskCheckStatus, string> = {
	pass: "✓",
	warn: "⚠",
	fail: "✗",
};

interface SignalDetailPanelProps {
	readonly signalId: string;
}

export function SignalDetailPanel({ signalId }: SignalDetailPanelProps) {
	const { data, isLoading, isError, refetch } = useSignalDetail(signalId);

	if (isLoading) {
		return (
			<Panel>
				<PanelHeader title="信号详情" />
				<PanelBody>
					<div className="p-3">
						<LoadingSkeleton variant="panel" rows={6} />
					</div>
				</PanelBody>
			</Panel>
		);
	}

	if (isError) {
		return (
			<Panel>
				<PanelHeader title="信号详情" />
				<PanelBody>
					<DittoErrorBoundary
						fallbackProps={{
							title: "信号详情加载失败",
							onRetry: () => void refetch(),
						}}
					>
						<div />
					</DittoErrorBoundary>
				</PanelBody>
			</Panel>
		);
	}

	return (
		<Panel>
			<PanelHeader title="信号详情" />
			<PanelBody>
				<div className="flex flex-col gap-(--density-gutter) p-3">
					<section>
						<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">
							AI 解读
						</h4>
						<p className="text-(length:--text-sm) leading-relaxed text-(--color-foreground)">
							{data?.explanation}
						</p>
					</section>

					<section>
						<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">
							风控检查
						</h4>
						<ul className="flex flex-col gap-1">
							{data?.riskChecks.map((check) => (
								<li
									key={check.name}
									className="flex items-start gap-2 text-(length:--text-sm)"
								>
									<span className={STATUS_STYLE[check.status as RiskCheckStatus]}>
										{STATUS_ICON[check.status as RiskCheckStatus]}
									</span>
									<div>
										<span className="font-medium text-(--color-foreground)">
											{check.name}
										</span>
										<span className="ml-1 text-(--color-foreground-tertiary)">
											{check.message}
										</span>
									</div>
								</li>
							))}
						</ul>
					</section>

					{data?.portfolioImpact && (
						<section>
							<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">
								组合影响
							</h4>
							<div className="grid grid-cols-3 gap-2 text-(length:--text-sm)">
								<div>
									<span className="text-(--color-foreground-tertiary)">集中度变化</span>
									<div className="font-data text-(--color-foreground)">
										{(data.portfolioImpact.concentrationChange * 100).toFixed(1)}%
									</div>
								</div>
								<div>
									<span className="text-(--color-foreground-tertiary)">行业暴露</span>
									<div className="font-data text-(--color-foreground)">
										{(data.portfolioImpact.sectorExposure * 100).toFixed(1)}%
									</div>
								</div>
								<div>
									<span className="text-(--color-foreground-tertiary)">风险变化</span>
									<div className="font-data text-(--color-foreground)">
										{(data.portfolioImpact.riskChange * 100).toFixed(1)}%
									</div>
								</div>
							</div>
						</section>
					)}

					{data?.actions && data.actions.length > 0 && (
						<section className="flex flex-wrap gap-2">
							{data.actions.map((action) => (
								<button
									key={action.type}
									type="button"
									disabled={!action.enabled}
									className={[
										"rounded-(--radius-sm) px-3 py-1.5 text-(length:--text-sm) font-medium",
										"border border-(--color-border-subtle)",
										action.enabled
											? "bg-(--color-surface-panel-base) text-(--color-foreground) hover:bg-(--color-interaction-hover-subtle-bg)"
											: "text-(--color-foreground-tertiary) opacity-50",
									].join(" ")}
								>
									{action.label}
								</button>
							))}
						</section>
					)}
				</div>
			</PanelBody>
		</Panel>
	);
}
