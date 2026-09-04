import { Link } from "@tanstack/react-router";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Panel, PanelBody, PanelHeader } from "@/features/shell/components/panel";
import { ApiError } from "@/lib/api-client";
import type { FactorCatalogItem } from "../api/factor-catalog";

function errorMessage(error: Error): string {
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "FACTOR_CATALOG_ERROR"}: ${error.message}`
		: error.message;
}

function metric(value: number | null, digits: number): string {
	return value === null ? "未评估" : value.toFixed(digits);
}

function percent(value: number | null): string {
	return value === null ? "未评估" : `${(value * 100).toFixed(1)}%`;
}

function statusLabel(value: string | null): string {
	if (value === "stable") return "稳定";
	if (value === "degrading") return "衰减";
	if (value === "warning") return "关注";
	return "未评估";
}

function statusClass(value: string | null): string {
	if (value === "stable") return "text-(--color-model-stable-fg)";
	if (value === "degrading") return "text-(--color-model-degrading-fg)";
	if (value === "warning") return "text-(--color-model-drifting-fg)";
	return "text-(--color-foreground-tertiary)";
}

export function ResearchFactorMonitor({
	rows,
	isLoading,
	error,
	onRetry,
}: {
	readonly rows: readonly FactorCatalogItem[];
	readonly isLoading: boolean;
	readonly error: Error | null;
	readonly onRetry: () => void;
}) {
	return (
		<section aria-label="因子监控" className="h-full min-h-0" data-info-level="l1" data-info-unit="factor-monitor">
			<Panel className="h-full [&>div:first-child]:h-10.5" data-testid="research-factor-monitor">
				<PanelHeader
					title="因子监控"
					count={rows.length}
					actions={
						<Link className="text-xs text-(--color-accent) hover:underline" to="/research/factors">
							完整因子目录
						</Link>
					}
				/>
				<PanelBody className="min-h-0 overflow-auto p-0">
					{error ? (
						<div className="flex flex-col items-start gap-2 p-4 text-sm text-(--color-led-danger)">
							<p role="alert">{errorMessage(error)}</p>
							<button type="button" className="underline" onClick={onRetry}>
								重试因子目录
							</button>
						</div>
					) : isLoading ? (
						<LoadingSkeleton variant="table" rows={8} />
					) : rows.length === 0 ? (
						<div className="p-4 text-sm text-(--color-foreground-tertiary)">
							<p>受控因子目录为空。</p>
							<p className="mt-1">系统不会回退到未注册因子或原型数据。</p>
						</div>
					) : (
						<table className="w-full min-w-3xl table-fixed border-collapse text-left text-xs">
							<colgroup>
								<col className="w-[21%]" />
								<col className="w-[8%]" />
								<col className="w-[8%]" />
								<col className="w-[8%]" />
								<col className="w-[9%]" />
								<col className="w-[8%]" />
								<col className="w-[10%]" />
								<col className="w-[11%]" />
								<col className="w-[17%]" />
							</colgroup>
							<thead className="sticky top-0 z-10 bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
								<tr className="h-6.5">
									<th className="pr-3 pl-9 font-medium">因子</th>
									<th className="px-2 text-right font-medium">Rank IC</th>
									<th className="px-2 text-right font-medium">IC_IR</th>
									<th className="px-2 text-right font-medium">Sharpe</th>
									<th className="px-2 text-right font-medium">换手率</th>
									<th className="px-2 text-right font-medium">衰减</th>
									<th className="px-2 text-right font-medium">覆盖率</th>
									<th className="px-2 font-medium">Universe</th>
									<th className="px-3 font-medium">状态</th>
								</tr>
							</thead>
							<tbody className="divide-y divide-(--color-border-subtle)">
								{rows.map((row) => {
									const preview = row.diagnosticPreview;
									return (
										<tr
											key={row.factorId}
											className="h-(--density-row-height) hover:bg-(--color-interaction-hover-subtle-bg)"
										>
											<td className="overflow-hidden pr-3 pl-9">
												<Link
													to="/research/factors/$id"
													params={{ id: row.factorId }}
													search={{ snapshotId: "", startDate: "", endDate: "", registryHash: "" }}
													className="block truncate font-data font-medium text-(--color-foreground) hover:text-(--color-accent)"
												>
													{row.factorId}
												</Link>
												<p className="mt-0.5 truncate text-xs text-(--color-foreground-tertiary)">
													{row.lanes.join(" / ") || "lane 未声明"} · {row.lookback} · {row.pitRequirement}
												</p>
											</td>
											<td className="px-2 text-right font-data tabular-nums">{metric(preview?.rankIc ?? null, 3)}</td>
											<td className="px-2 text-right font-data tabular-nums">{metric(preview?.icIr ?? null, 2)}</td>
											<td className="px-2 text-right font-data tabular-nums">{metric(preview?.sharpe ?? null, 2)}</td>
											<td className="px-2 text-right font-data tabular-nums">{percent(preview?.turnover ?? null)}</td>
											<td className="px-2 text-right font-data tabular-nums">{percent(preview?.decay ?? null)}</td>
											<td className="px-2 text-right font-data tabular-nums">{percent(preview?.coverage ?? null)}</td>
											<td className="px-2 text-(--color-foreground-secondary)">{preview?.universe ?? "未评估"}</td>
											<td className={`px-3 font-medium ${statusClass(preview?.status ?? null)}`}>
												{statusLabel(preview?.status ?? null)}
											</td>
										</tr>
									);
								})}
							</tbody>
						</table>
					)}
				</PanelBody>
			</Panel>
		</section>
	);
}
