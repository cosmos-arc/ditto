import { useState } from "react";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { PortfolioComparison } from "../api/portfolio-comparison";
import {
	DRIFT_PAIRS,
	type DriftPairId,
	driftRows,
	driftScaleBucket,
	formatDriftBps,
	isDriftEmpty,
	maxAbsDriftBps,
} from "../lib/drift-chart-mapping";

/**
 * 三组合权重漂移对比（单 as_of 快照读模型，CR #215 收窄交付）。
 *
 * - 每 pair 一列，列头即图例开关（aria-pressed），控制该列显隐；
 * - 每格为发散条：观察侧超配向右、低配向左，宽度按可见列内最大 |bps| 归一；
 * - as_of / valuation snapshot 在图头可见——三列共享同一 PIT 快照（mismatch 由
 *   页面身份断言 fail closed，图内不重算）。
 */
export function PortfolioDriftChart({ comparison }: { readonly comparison: PortfolioComparison }) {
	const [hiddenPairs, setHiddenPairs] = useState<ReadonlySet<DriftPairId>>(new Set());
	const visiblePairs = DRIFT_PAIRS.filter((pair) => !hiddenPairs.has(pair.id));
	const rows = driftRows(comparison);
	const empty = isDriftEmpty(comparison);
	const scale = maxAbsDriftBps(
		rows,
		visiblePairs.map((pair) => pair.id),
	);

	const togglePair = (pairId: DriftPairId) => {
		setHiddenPairs((previous) => {
			const next = new Set(previous);
			if (next.has(pairId)) {
				next.delete(pairId);
			} else {
				next.add(pairId);
			}
			return next;
		});
	};

	if (empty) {
		return (
			<Panel data-testid="portfolio-drift-chart" data-state="drift-empty">
				<PanelHeader title="Drift / 权重漂移对比" />
				<PanelBody className="p-(--density-panel-padding)">
					<p className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-3 py-4 text-sm text-(--color-foreground-secondary)">
						三组合在 AS OF {comparison.as_of} 无权重漂移数据。
					</p>
				</PanelBody>
			</Panel>
		);
	}

	return (
		<Panel data-testid="portfolio-drift-chart">
			<PanelHeader
				title="Drift / 权重漂移对比"
				actions={
					<span data-testid="drift-as-of" className="font-data text-xs text-(--color-foreground-tertiary)">
						AS OF {comparison.as_of} · 同快照对比
					</span>
				}
			/>
			<PanelBody className="p-(--density-panel-padding)">
				<div className="grid grid-cols-[minmax(5rem,0.6fr)_repeat(3,minmax(0,1fr))] gap-x-3 gap-y-1 text-xs">
					<span className="flex items-end pb-2 uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">
						标的 / 组合
					</span>
					{DRIFT_PAIRS.map((pair) => {
						const visible = !hiddenPairs.has(pair.id);
						return (
							<button
								key={pair.id}
								type="button"
								aria-pressed={visible}
								data-pair={pair.id}
								data-pair-visible={visible}
								onClick={() => togglePair(pair.id)}
								className="flex items-center gap-1.5 pb-2 text-left font-data text-[11px] tracking-[0.04em] text-(--color-foreground-tertiary) transition-opacity hover:text-(--color-foreground-secondary)"
							>
								<span aria-hidden="true" className="drift-pair-dot" data-pair={pair.id} />
								<span className={visible ? "" : "line-through opacity-60"}>{pair.label}</span>
								<span className="tabular-nums opacity-70">
									Σ {formatDriftBps(Number(comparison[pair.id].total_abs_drift_bps))}
								</span>
							</button>
						);
					})}
					{rows.map((row) => (
						<div
							key={row.key}
							className="col-span-full grid grid-cols-subgrid border-t border-(--color-border-subtle) py-2"
						>
							<span className="font-data text-(--color-foreground-secondary)">{row.label}</span>
							{DRIFT_PAIRS.map((pair) => {
								if (hiddenPairs.has(pair.id)) {
									return (
										<span
											key={pair.id}
											data-testid={`drift-cell-${row.key}-${pair.id}`}
											className="text-(--color-foreground-tertiary)"
											aria-hidden="true"
										/>
									);
								}
								const value = row.driftBps[pair.id];
								const bucket = driftScaleBucket(value, scale);
								return (
									<span
										key={pair.id}
										data-testid={`drift-cell-${row.key}-${pair.id}`}
										className="flex items-center gap-2 font-data tabular-nums text-(--color-foreground)"
									>
										<span className="drift-bar" data-pair={pair.id}>
											<span className="drift-bar-axis" aria-hidden="true" />
											{bucket > 0 ? (
												<span
													className="drift-bar-fill"
													data-pair={pair.id}
													data-side={(value ?? 0) >= 0 ? "pos" : "neg"}
													data-scale={bucket}
												/>
											) : null}
										</span>
										<span>{value === undefined ? "—" : formatDriftBps(value)}</span>
									</span>
								);
							})}
						</div>
					))}
					{visiblePairs.length === 0 && (
						<p
							className="col-span-full border-t border-(--color-border-subtle) py-6 text-center text-xs text-(--color-foreground-tertiary)"
							data-state="all-pairs-hidden"
						>
							全部对比列已隐藏——点击任一列头恢复
						</p>
					)}
				</div>
				<p className="mt-3 border-t border-(--color-border-subtle) pt-2 text-[11px] text-(--color-foreground-tertiary)">
					发散条按可见列最大 |bps| 归一；右 = 观察侧超配，左 = 观察侧低配。三列共享 valuation snapshot
					{/* 不加 title：页头已提供完整快照 id 的悬停入口，重复 title 会破坏 getByTitle 严格定位 */}
					<span className="ml-1 max-w-56 truncate font-data">{comparison.valuation_snapshot_id}</span>
					，as_of 不一致时页面整体 fail closed，不会出现混合水位图。
				</p>
			</PanelBody>
		</Panel>
	);
}
