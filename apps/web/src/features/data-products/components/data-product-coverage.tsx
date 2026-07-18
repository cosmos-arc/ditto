import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { DataProductCoverage as DataProductCoverageModel } from "../api";

interface DataProductCoverageProps {
	readonly data?: DataProductCoverageModel;
	readonly isLoading: boolean;
	readonly isError: boolean;
}

const MILESTONES = [
	["Raw 起点", "raw_from"],
	["Complete 起点", "complete_from"],
	["Certified 起点", "certified_from"],
] as const;

export function DataProductCoverage({ data, isLoading, isError }: DataProductCoverageProps) {
	return (
		<Panel className="h-full" data-info-level="l1" data-info-unit="data-product-coverage">
			<PanelHeader title="Coverage Timeline" subtitle={data?.profile ?? "research_daily"} />
			<PanelBody className="p-(--density-panel-padding)">
				{isLoading && (
					<div
						role="status"
						aria-label="正在加载覆盖证据"
						className="h-24 animate-pulse rounded-(--radius-sm) bg-(--color-surface-muted)"
					/>
				)}
				{isError && (
					<p role="alert" className="text-sm text-(--color-risk-critical-fg)">
						覆盖证据暂不可用，请检查认证报告。
					</p>
				)}
				{data && (
					<div className="flex flex-col gap-5">
						<ol aria-label="三类覆盖起点" className="grid gap-2 sm:grid-cols-3">
							{MILESTONES.map(([label, key], index) => (
								<li
									key={key}
									className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-panel-elevated) p-3"
								>
									<span className="font-data text-xs text-(--color-foreground-tertiary)">0{index + 1}</span>
									<p className="mt-2 text-xs text-(--color-foreground-secondary)">{label}</p>
									<p className="mt-1 font-data text-sm tabular-nums text-(--color-foreground)">
										{data[key] ?? "未建立"}
									</p>
								</li>
							))}
						</ol>
						<section aria-label="Partition coverage" className="border-t border-(--color-border-subtle) pt-4">
							<div className="flex flex-wrap items-baseline justify-between gap-2">
								<div>
									<p className="text-xs text-(--color-foreground-tertiary)">Partition coverage</p>
									<p className="mt-1 font-data text-lg tabular-nums text-(--color-foreground)">
										{data.actual_partitions} / {data.expected_partitions}
									</p>
								</div>
								<span className="rounded-(--radius-sm) bg-(--color-risk-high-bg) px-2 py-1 text-xs font-medium text-(--color-risk-high-fg)">
									未批准缺口 {data.unapproved_gaps.length}
								</span>
							</div>
							<div className="mt-3 flex flex-wrap gap-2">
								{data.gaps.length === 0 ? (
									<span className="text-xs text-(--color-system-healthy-fg)">完整，无缺口</span>
								) : (
									data.gaps.map((gap) => (
										<code
											key={gap}
											className="rounded-(--radius-sm) bg-(--color-surface-muted) px-2 py-1 font-code text-xs text-(--color-risk-high-fg)"
										>
											{gap}
										</code>
									))
								)}
							</div>
						</section>
					</div>
				)}
			</PanelBody>
		</Panel>
	);
}
