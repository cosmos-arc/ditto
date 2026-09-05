import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { DataProductRun } from "../api";
import { OperationPreview } from "./operation-preview";

interface DataProductRunsProps {
	readonly datasetId: string;
	readonly data?: readonly DataProductRun[] | undefined;
	readonly isLoading: boolean;
	readonly isError: boolean;
}

export function DataProductRuns({ datasetId, data, isLoading, isError }: DataProductRunsProps) {
	return (
		<Panel className="h-full" data-info-level="l1" data-info-unit="data-product-runs">
			<PanelHeader title="Runs & Repair" count={data?.length} />
			<PanelBody className="p-(--density-panel-padding)">
				{isLoading && (
					<div
						role="status"
						aria-label="正在加载运行证据"
						className="h-24 animate-pulse rounded-(--radius-sm) bg-(--color-surface-muted)"
					/>
				)}
				{isError && (
					<p role="alert" className="text-sm text-(--color-risk-critical-fg)">
						运行记录暂不可用。
					</p>
				)}
				{data && (
					<section aria-label="不可变认证运行">
						<div className="overflow-x-auto">
							<table className="w-full min-w-[38rem] text-left text-xs">
								<thead className="text-(--color-foreground-tertiary)">
									<tr className="border-b border-(--color-border-subtle)">
										<th className="px-2 py-2 font-medium">Report</th>
										<th className="px-2 py-2 font-medium">Generated</th>
										<th className="px-2 py-2 font-medium">Status</th>
										<th className="px-2 py-2 font-medium">Reviewer</th>
									</tr>
								</thead>
								<tbody>
									{data.map((run) => (
										<tr key={run.report_id} className="border-b border-(--color-border-subtle)">
											<td className="px-2 py-2 font-code text-(--color-foreground)">{run.report_id}</td>
											<td className="px-2 py-2 font-data tabular-nums text-(--color-foreground-secondary)">
												{run.generated_at}
											</td>
											<td className="px-2 py-2 text-(--color-system-healthy-fg)">✓ {run.status}</td>
											<td className="px-2 py-2 text-(--color-foreground-secondary)">{run.reviewed_by ?? "未复核"}</td>
										</tr>
									))}
								</tbody>
							</table>
						</div>
						{data.length === 0 && (
							<p className="py-4 text-xs text-(--color-foreground-tertiary)">尚无认证运行，先 preview bootstrap。</p>
						)}
					</section>
				)}
				<section aria-label="Chunk 修复与重试" className="mt-5 border-t border-(--color-border-subtle) pt-4">
					<h3 className="text-sm font-medium text-(--color-foreground)">Chunk 修复与重试</h3>
					<p className="mt-1 max-w-[68ch] text-xs text-(--color-foreground-secondary)">
						Bootstrap 与 repair 使用 schedule-aware planner、checkpoint
						和隔离写入。先预览，再生成需要人工执行的确认指令。
					</p>
					<div className="mt-3">
						<OperationPreview datasetId={datasetId} operations={["bootstrap", "repair"]} />
					</div>
				</section>
			</PanelBody>
		</Panel>
	);
}
