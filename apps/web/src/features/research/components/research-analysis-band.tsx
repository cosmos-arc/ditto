import { Link } from "@tanstack/react-router";
import { useState } from "react";
import type { FactorCatalogItem } from "../api/factor-catalog";

const TABS = ["IC 趋势", "因子宽度", "相关性", "备注"] as const;

export function ResearchAnalysisBand({ factors }: { readonly factors: readonly FactorCatalogItem[] }) {
	const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>("IC 趋势");
	const evaluated = factors.filter((factor) => factor.diagnosticPreview?.rankIc !== null);
	const averageIc =
		evaluated.length === 0
			? null
			: evaluated.reduce((sum, factor) => sum + (factor.diagnosticPreview?.rankIc ?? 0), 0) / evaluated.length;

	return (
		<section
			aria-label="研究分析"
			className="h-full border-t border-(--color-border-subtle)"
			data-info-level="l2"
			data-info-unit="research-analysis"
		>
			<div
				role="tablist"
				aria-label="研究分析维度"
				className="flex h-(--density-header-height) items-center gap-1 bg-(--color-surface-strip) px-2"
			>
				{TABS.map((tab) => (
					<button
						key={tab}
						type="button"
						role="tab"
						aria-selected={tab === activeTab}
						className={`rounded-(--radius-sm) px-3 py-1 text-xs ${
							tab === activeTab
								? "bg-(--color-surface-panel-elevated) font-medium text-(--color-foreground)"
								: "text-(--color-foreground-tertiary) hover:bg-(--color-interaction-hover-subtle-bg)"
						}`}
						onClick={() => setActiveTab(tab)}
					>
						{tab}
					</button>
				))}
			</div>
			<div
				role="tabpanel"
				className="grid h-[calc(100%-var(--density-header-height))] grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4"
			>
				<div>
					<p className="text-xs font-medium text-(--color-foreground)">{activeTab}</p>
					{averageIc === null ? (
						<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
							当前没有绑定 snapshot、registry hash 与折叠窗口的诊断证据，不展示推测值。
						</p>
					) : (
						<p className="mt-1 font-data text-sm tabular-nums text-(--color-model-stable-fg)">
							原型诊断预览 · {evaluated.length} 因子 · 平均 Rank IC {averageIc.toFixed(3)}
						</p>
					)}
				</div>
				<Link
					to="/research/factors"
					className="rounded-(--radius-sm) border border-(--color-border) px-3 py-1.5 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
				>
					打开因子分析
				</Link>
			</div>
		</section>
	);
}
