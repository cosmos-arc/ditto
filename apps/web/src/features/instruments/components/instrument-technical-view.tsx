import { type ReactNode, useEffect } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import { ErrorState } from "@/lib/error-boundary";
import type { TechnicalAnalysisDirection, TechnicalAnalysisIndicator } from "../api/technical-analysis";
import {
	type InstrumentTechnicalDependencies,
	useInstrumentTechnicalAnalysis,
} from "../hooks/use-instrument-technical-analysis";

type Direction = TechnicalAnalysisDirection;
type Reading = TechnicalAnalysisIndicator;

const DIRECTION_LABEL: Record<Direction, string> = {
	bearish: "偏空",
	bullish: "偏多",
	neutral: "中性",
	unknown: "未知",
};

function shortIdentity(value: string): string {
	const digest = value.split(":sha256:").at(-1);
	return digest ? `${value.split(":sha256:")[0]} · ${digest.slice(0, 12)}` : value;
}

function DirectionMark({ value }: { readonly value: Direction }) {
	const glyph = value === "bullish" ? "↗" : value === "bearish" ? "↘" : "→";
	const className =
		value === "bullish"
			? "text-(--color-market-up)"
			: value === "bearish"
				? "text-(--color-market-down)"
				: "text-(--color-foreground-tertiary)";
	return (
		<span className={`inline-flex items-center gap-1 font-medium ${className}`}>
			<span aria-hidden="true">{glyph}</span>
			{DIRECTION_LABEL[value]}
		</span>
	);
}

function Metric({ label, children }: { readonly label: string; readonly children: ReactNode }) {
	return (
		<div className="border-l border-(--color-border-subtle) pl-3 first:border-l-0 first:pl-0">
			<p className="text-xs uppercase tracking-[0.14em] text-(--color-foreground-tertiary)">{label}</p>
			<div className="mt-1 font-mono text-sm text-(--color-foreground)">{children}</div>
		</div>
	);
}

function ReadingValue({ reading }: { readonly reading: Reading }) {
	if (reading.status !== "ready" || reading.value === null) {
		return <span className="text-(--color-foreground-tertiary)">{reading.status}</span>;
	}
	return <span>{reading.value.toLocaleString("zh-CN", { maximumFractionDigits: 4 })}</span>;
}

export function InstrumentTechnicalView({
	dependencies,
	id,
	onSnapshotIdentity,
	selectionRunId,
}: {
	readonly dependencies: InstrumentTechnicalDependencies;
	readonly id: string;
	readonly onSnapshotIdentity?: (snapshotId: string | null) => void;
	readonly selectionRunId: string | undefined;
}) {
	const { analysis, candidate, exclusion, identity, selection, sourceEvidence } = useInstrumentTechnicalAnalysis(
		id,
		selectionRunId,
		dependencies,
	);

	useEffect(() => {
		onSnapshotIdentity?.(analysis.data?.snapshot_id ?? null);
	}, [analysis.data?.snapshot_id, onSnapshotIdentity]);

	if (!selectionRunId) {
		return (
			<div className="grid min-h-80 place-items-center p-8">
				<div className="max-w-lg border-l-2 border-(--color-risk-warning-fg) pl-5">
					<p className="text-sm font-semibold text-(--color-foreground)">需要精确证据上下文</p>
					<p className="mt-2 text-xs leading-5 text-(--color-foreground-tertiary)">
						请从 Selection Workspace 的已保存候选进入。技术分析不会猜测 knowledge cutoff、publication cutoff 或 source
						snapshot。
					</p>
				</div>
			</div>
		);
	}

	if (selection.isLoading || identity.isLoading || sourceEvidence.isLoading || analysis.isLoading) {
		return <LoadingSkeleton variant="panel" rows={8} />;
	}
	if (selection.isError || identity.isError || sourceEvidence.isError || analysis.isError) {
		return (
			<ErrorState
				onRetry={() =>
					void Promise.all([selection.refetch(), identity.refetch(), sourceEvidence.refetch(), analysis.refetch()])
				}
			/>
		);
	}
	if (!selection.data || (!candidate && !exclusion)) {
		return (
			<div className="grid min-h-80 place-items-center p-8 text-sm text-(--color-risk-warning-fg)">
				该 SelectionRun 不包含当前标的，技术证据已阻塞。
			</div>
		);
	}
	if (!analysis.data) return null;

	const snapshot = analysis.data;
	const statusVariant =
		snapshot.status === "ready" ? "healthy" : snapshot.status === "degraded" ? "warning" : "critical";

	return (
		<div className="h-full overflow-y-auto bg-(--color-surface-0) p-3 text-sm">
			<div className="mx-auto grid max-w-[1500px] gap-3 xl:grid-cols-[minmax(0,1fr)_21rem]">
				<main className="min-w-0 space-y-3">
					<section
						className="border border-(--color-border-subtle) bg-(--color-surface-panel-base)"
						data-info-level="l2"
						data-info-unit="technical-snapshot"
					>
						<header className="flex flex-wrap items-start justify-between gap-4 border-b border-(--color-border-subtle) px-4 py-3">
							<div>
								<div className="flex items-center gap-2">
									<span aria-hidden="true" className="font-mono text-xs font-bold text-(--color-accent)">
										TA
									</span>
									<h2 className="font-semibold">技术证据快照</h2>
									<StatusBadge label={snapshot.status.toUpperCase()} size="sm" variant={statusVariant} />
								</div>
								<p className="mt-1 font-mono text-[11px] text-(--color-foreground-tertiary)">
									{shortIdentity(snapshot.snapshot_id)}
								</p>
							</div>
							<p className="max-w-md text-right text-[11px] leading-5 text-(--color-foreground-tertiary)">
								仅基于 cutoff 前可见的已认证日线；所有指标、价位与冲突均来自同一内容寻址快照。
							</p>
						</header>
						<div className="grid gap-3 px-4 py-3 sm:grid-cols-2 xl:grid-cols-4">
							<Metric label="As of">{new Date(snapshot.as_of).toLocaleString("zh-CN", { hour12: false })}</Metric>
							<Metric label="Last visible">{snapshot.last_visible_bar_at ?? "—"}</Metric>
							<Metric label="Registry">{snapshot.registry_version}</Metric>
							<Metric label="Readings">{snapshot.readings.length}</Metric>
						</div>
					</section>

					<section className="grid gap-3 md:grid-cols-2" aria-label="时间框架摘要">
						{snapshot.timeframe_summaries.map((summary) => (
							<article
								key={summary.timeframe}
								className="border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-4"
							>
								<div className="mb-4 flex items-center justify-between">
									<h3 className="font-semibold">{summary.timeframe === "daily" ? "日线结构" : "周线结构"}</h3>
									<span className="font-mono text-xs uppercase tracking-[0.16em] text-(--color-foreground-tertiary)">
										{summary.timeframe}
									</span>
								</div>
								<div className="grid grid-cols-3 gap-2">
									<Metric label="Trend">
										<DirectionMark value={summary.trend} />
									</Metric>
									<Metric label="Momentum">
										<DirectionMark value={summary.momentum} />
									</Metric>
									<Metric label="Breakout">
										<DirectionMark value={summary.breakout} />
									</Metric>
								</div>
							</article>
						))}
					</section>

					{snapshot.missing_inputs.length > 0 && (
						<section
							className="border border-(--color-risk-warning-fg)/40 bg-(--color-risk-warning-bg) px-4 py-3"
							data-info-level="l2"
							data-info-unit="technical-missing-inputs"
						>
							<h3 className="text-xs font-semibold text-(--color-risk-warning-fg)">MISSING INPUTS</h3>
							<ul className="mt-2 space-y-1 font-mono text-xs text-(--color-foreground-tertiary)">
								{snapshot.missing_inputs.map((item) => (
									<li key={item} className="break-all">
										{item}
									</li>
								))}
							</ul>
						</section>
					)}

					{snapshot.conflicts.length > 0 && (
						<section
							className="border border-(--color-risk-warning-fg)/40 bg-(--color-risk-warning-bg) px-4 py-3"
							data-info-level="l2"
							data-info-unit="technical-conflicts"
						>
							<div className="flex items-center gap-2 text-(--color-risk-warning-fg)">
								<span aria-hidden="true" className="font-mono font-bold">
									!
								</span>
								<h3 className="font-semibold">日线 / 周线冲突</h3>
							</div>
							<div className="mt-2 grid gap-2 md:grid-cols-3">
								{snapshot.conflicts.map((conflict) => (
									<div key={conflict.dimension} className="flex items-center justify-between gap-3 text-xs">
										<span className="font-mono uppercase">{conflict.dimension}</span>
										<span>
											<DirectionMark value={conflict.daily} /> → <DirectionMark value={conflict.weekly} />
										</span>
									</div>
								))}
							</div>
						</section>
					)}

					<section
						className="border border-(--color-border-subtle) bg-(--color-surface-panel-base)"
						data-info-level="l2"
						data-info-unit="technical-readings"
					>
						<div className="flex items-center justify-between border-b border-(--color-border-subtle) px-4 py-2.5">
							<h3 className="font-semibold">指标矩阵</h3>
							<span className="text-[11px] text-(--color-foreground-tertiary)">固定 v1 注册表 · warm-up 显式呈现</span>
						</div>
						<div className="overflow-x-auto">
							<table className="w-full text-left text-xs">
								<thead className="bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
									<tr>
										<th className="px-4 py-2">Timeframe</th>
										<th className="px-4 py-2">Indicator</th>
										<th className="px-4 py-2">Value</th>
										<th className="px-4 py-2">Window</th>
										<th className="px-4 py-2">Version</th>
										<th className="px-4 py-2">State</th>
									</tr>
								</thead>
								<tbody className="divide-y divide-(--color-border-subtle)">
									{snapshot.readings.map((reading) => (
										<tr key={`${reading.timeframe}-${reading.name}`}>
											<td className="px-4 py-2 font-mono uppercase">{reading.timeframe}</td>
											<td className="px-4 py-2 font-medium">{reading.name}</td>
											<td className="px-4 py-2 font-mono">
												<ReadingValue reading={reading} />
											</td>
											<td className="px-4 py-2 font-mono">{reading.window ?? "—"}</td>
											<td className="px-4 py-2 font-mono text-(--color-foreground-tertiary)">
												{reading.indicator_version}
											</td>
											<td className="px-4 py-2">
												<StatusBadge
													label={reading.status}
													size="sm"
													variant={reading.status === "ready" ? "healthy" : "warning"}
												/>
											</td>
										</tr>
									))}
								</tbody>
							</table>
						</div>
					</section>
				</main>

				<aside className="min-w-0 space-y-3" data-info-level="l2" data-info-unit="technical-inspector">
					<Panel>
						<PanelHeader title="Selection Inspector" subtitle={shortIdentity(selection.data.run_id)} />
						<PanelBody className="space-y-4 p-4">
							{candidate ? (
								<>
									<div className="grid grid-cols-2 gap-3">
										<Metric label="Rank">#{candidate.rank}</Metric>
										<Metric label="Score">{candidate.score.toFixed(4)}</Metric>
									</div>
									<div>
										<p className="mb-2 text-xs uppercase tracking-[0.14em] text-(--color-foreground-tertiary)">
											Factor contribution
										</p>
										<div className="space-y-2">
											{candidate.factor_contributions.map((factor) => (
												<div
													key={factor.factor_name}
													className="flex items-center justify-between border-b border-(--color-border-subtle) pb-2 text-xs"
												>
													<span>{factor.factor_name}</span>
													<span className="font-mono">{factor.contribution.toFixed(4)}</span>
												</div>
											))}
										</div>
									</div>
								</>
							) : (
								<div className="border-l-2 border-(--color-risk-warning-fg) pl-3 text-xs">
									<p className="font-mono text-(--color-risk-warning-fg)">{exclusion?.reason_code}</p>
									<p className="mt-1 text-(--color-foreground-tertiary)">{exclusion?.detail}</p>
									<p className="mt-1 uppercase text-(--color-foreground-tertiary)">{exclusion?.stage}</p>
								</div>
							)}
						</PanelBody>
					</Panel>

					<Panel>
						<PanelHeader title="关键价位" subtitle="deterministic · versioned" />
						<PanelBody className="space-y-2 p-4">
							{snapshot.levels.map((level) => (
								<div
									key={`${level.kind}-${level.timeframe}-${level.price}`}
									className="border-l-2 border-(--color-accent) py-1 pl-3"
								>
									<div className="flex items-baseline justify-between gap-3">
										<span className="text-xs font-medium">
											{level.kind === "support" ? "支撑" : "阻力"} · {level.timeframe}
										</span>
										<span className="font-mono text-base">
											{level.price.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
										</span>
									</div>
									<p className="mt-1 font-mono text-xs text-(--color-foreground-tertiary)">
										confidence {(level.confidence * 100).toFixed(0)}% · {level.touches} touches · w{level.window}
									</p>
								</div>
							))}
						</PanelBody>
					</Panel>

					<Panel>
						<PanelHeader title="LINEAGE" subtitle="exact identities" />
						<PanelBody className="space-y-3 p-4 text-[11px]">
							<div className="flex items-center gap-2 text-(--color-foreground-secondary)">
								<span aria-hidden="true" className="font-mono">
									∷
								</span>{" "}
								Source snapshots
							</div>
							<ul className="space-y-1 font-mono text-(--color-foreground-tertiary)">
								{snapshot.source_snapshot_ids.map((item) => (
									<li key={item} className="break-all">
										{item}
									</li>
								))}
							</ul>
							<dl className="grid grid-cols-[4rem_1fr] gap-x-2 gap-y-1 border-t border-(--color-border-subtle) pt-3">
								<dt>Spec</dt>
								<dd className="break-all font-mono">{snapshot.spec_hash}</dd>
								<dt>Input</dt>
								<dd className="break-all font-mono">{snapshot.input_hash}</dd>
							</dl>
						</PanelBody>
					</Panel>
				</aside>
			</div>
		</div>
	);
}
