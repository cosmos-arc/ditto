import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Panel, PanelBody, PanelHeader } from "@/features/shell/components/panel";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useAgentFindings } from "../hooks";

const ICON_COLOR: Record<string, string> = {
	insight: "text-(--color-system-healthy-fg)",
	warning: "text-(--color-system-degraded-fg)",
	info: "text-(--color-brand-500)",
};

/**
 * ResearchProgressSection — "研究进展" secondary panel.
 * Matches prototype .secondary-panel with .research-item rows.
 */
export function ResearchProgressSection() {
	const { data: findingsData, isLoading, refetch } = useAgentFindings();

	return (
		<Panel className="min-h-0 overflow-hidden" data-info-level="l2" data-info-unit="research-progress">
			<PanelHeader
				title="研究进展"
				subtitle="研究动态"
				actions={
					<button
						type="button"
						className="text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) rounded-[var(--radius-sm)] px-1.5 py-0.5"
					>
						查看全部 →
					</button>
				}
			/>
			<PanelBody>
				{isLoading && <LoadingSkeleton variant="table" rows={3} />}
				<DittoErrorBoundary
					fallbackProps={{
						title: "研究进展加载失败",
						onRetry: () => void refetch(),
					}}
				>
					{findingsData && (
						<div className="flex flex-col">
							{findingsData.findings.map((finding, i) => (
								<div
									key={`${finding.source}-${i}`}
									className="flex gap-2 rounded-[4px] p-1 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<span
										className={`mt-0.5 shrink-0 ${ICON_COLOR[finding.icon] ?? "text-(--color-foreground-tertiary)"}`}
									>
										<svg width={14} height={14} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.5}>
											{finding.icon === "warning" ? (
												<path d="M10 3L3 17h14L10 3z" />
											) : finding.icon === "insight" ? (
												<path d="M4 10l3 3 9-9" />
											) : (
												<circle cx="10" cy="10" r="8" />
											)}
										</svg>
									</span>
									<div className="min-w-0 flex-1">
										<p className="text-(--color-foreground)">{finding.summary ?? finding.text}</p>
										<span className="text-xs tabular-nums text-(--color-foreground-tertiary)">
											{finding.time ?? finding.source}
										</span>
									</div>
								</div>
							))}
						</div>
					)}
				</DittoErrorBoundary>
			</PanelBody>
		</Panel>
	);
}
