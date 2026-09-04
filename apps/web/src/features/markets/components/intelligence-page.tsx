import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { AnalyticalLayout, StatusBar } from "@/features/shell";
import { Panel, PanelBody, PanelHeader } from "@/features/shell/components/panel";
import { ErrorState } from "@/lib/error-boundary";
import { useMacroEvidence } from "../hooks";
import { IntelligenceOverlay, type IntelligenceOverlayId, intelligenceActions } from "./market-page-overlays";

export function IntelligencePage() {
	const [startDate, setStartDate] = useState("2026-01-01");
	const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10));
	const [allowExperimental, setAllowExperimental] = useState(false);
	const [activeOverlay, setActiveOverlay] = useState<IntelligenceOverlayId | null>(null);
	const [bookmarked, setBookmarked] = useState(false);
	const query = useMacroEvidence({
		allowExperimentalData: allowExperimental,
		endDate,
		startDate,
	});

	function openOverlay(id: IntelligenceOverlayId): void {
		if (id === "bookmark-success") setBookmarked(true);
		setActiveOverlay(id);
	}

	return (
		<>
			<AnalyticalLayout
				className="pb-(--height-status-bar) [--height-analysis-band:48px]"
				strip={
					<div
						data-info-level="l1"
						data-info-unit="intelligence-controls"
						className="flex flex-wrap items-end gap-[var(--section-gap)] border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2"
					>
						<div>
							<p className="text-sm font-medium">宏观证据浏览器</p>
							<p className="text-xs text-(--color-foreground-tertiary)">公开 experimental API · 用户显式 opt-in</p>
						</div>
						<label className="grid gap-1 text-xs text-(--color-foreground-tertiary)">
							开始日期
							<input
								aria-label="开始日期"
								type="date"
								value={startDate}
								onChange={(event) => setStartDate(event.currentTarget.value)}
								className="rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1 text-sm text-(--color-foreground)"
							/>
						</label>
						<label className="grid gap-1 text-xs text-(--color-foreground-tertiary)">
							截至日期
							<input
								aria-label="截至日期"
								type="date"
								value={endDate}
								onChange={(event) => setEndDate(event.currentTarget.value)}
								className="rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1 text-sm text-(--color-foreground)"
							/>
						</label>
						<label className="flex items-center gap-2 rounded-md border border-(--color-border-subtle) bg-(--color-surface-1) px-3 py-2 text-sm">
							<input
								type="checkbox"
								checked={allowExperimental}
								onChange={(event) => setAllowExperimental(event.currentTarget.checked)}
							/>
							允许 experimental 宏观数据
						</label>
						{bookmarked && <span className="text-xs text-(--color-system-healthy-fg)">视角已收藏</span>}
						<PageActionBar ariaLabel="情报页面操作" actions={intelligenceActions} onOpen={openOverlay} />
					</div>
				}
				main={
					<div className="h-full overflow-y-auto p-(--density-panel-padding)">
						<ContextSection title="宏观指标" data-info-level="l1" data-info-unit="macro-evidence">
							{!allowExperimental && (
								<div className="p-10 text-center">
									<p className="font-medium text-(--color-foreground)">实验数据未启用</p>
									<p className="mt-1 text-sm text-(--color-foreground-tertiary)">
										勾选上方开关后，才会按所选日期范围发起读取。
									</p>
								</div>
							)}
							{allowExperimental && query.isLoading && <LoadingSkeleton variant="table" rows={7} />}
							{allowExperimental && query.isError && <ErrorState onRetry={() => void query.refetch()} />}
							{allowExperimental && query.data?.length === 0 && (
								<div className="p-10 text-center text-sm text-(--color-foreground-tertiary)">
									所选日期范围没有宏观指标
								</div>
							)}
							{allowExperimental && query.data && query.data.length > 0 && (
								<div className="overflow-x-auto">
									<table className="w-full text-sm">
										<thead className="text-left text-xs text-(--color-foreground-tertiary)">
											<tr>
												{["指标", "代码", "类别", "频率", "观测日期", "数值"].map((label) => (
													<th key={label} className="px-3 py-2 font-medium">
														{label}
													</th>
												))}
											</tr>
										</thead>
										<tbody>
											{query.data.map((indicator) => (
												<tr
													key={indicator.indicator_id}
													data-info-level="l3"
													data-info-unit="macro-indicator-row"
													className="border-t border-(--color-border-subtle)"
												>
													<td className="px-3 py-2 font-medium">{indicator.name}</td>
													<td className="px-3 py-2 font-mono text-xs">{indicator.code}</td>
													<td className="px-3 py-2">{indicator.category}</td>
													<td className="px-3 py-2">{indicator.frequency}</td>
													<td className="px-3 py-2 font-mono">{indicator.date}</td>
													<td className="px-3 py-2 font-data font-semibold">
														{indicator.value.toLocaleString()}
														{indicator.unit ?? ""}
													</td>
												</tr>
											))}
										</tbody>
									</table>
								</div>
							)}
						</ContextSection>
					</div>
				}
				activity={
					<Panel data-info-level="l1" data-info-unit="intelligence-boundary">
						<PanelHeader title="证据边界" />
						<PanelBody className="space-y-3 p-4 text-sm leading-6 text-(--color-foreground-secondary)">
							<p>查询日期由操作者明确选择；experimental 默认为关闭。</p>
							<p className="rounded-md border border-(--color-risk-warning)/30 bg-(--color-risk-warning)/5 p-3 text-(--color-risk-warning)">
								snapshot identity 未报告，结果仅用于研究浏览，不自动生成 AI 解读、市场结论或交易建议。
							</p>
						</PanelBody>
					</Panel>
				}
				analysis={
					<div
						data-info-level="l2"
						data-info-unit="intelligence-decision-boundary"
						className="border-t border-(--color-border-subtle) bg-(--color-surface-0) px-4 py-2 text-xs text-(--color-foreground-tertiary)"
					>
						自动解读关闭 · 只有 immutable snapshot 与可追溯模型输出同时可用时才开放决策摘要
					</div>
				}
			/>
			<StatusBar />
			<IntelligenceOverlay
				active={activeOverlay}
				allowExperimental={allowExperimental}
				endDate={endDate}
				indicatorCount={query.data?.length ?? 0}
				onClearBookmark={() => {
					setBookmarked(false);
					setActiveOverlay(null);
				}}
				onClose={() => setActiveOverlay(null)}
				startDate={startDate}
			/>
		</>
	);
}
