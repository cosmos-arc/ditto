import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { ErrorState } from "@/lib/error-boundary";
import { useInstrumentChart } from "../hooks";

interface InstrumentChartViewProps {
	readonly id: string;
}

function dateDaysAgo(days: number): string {
	const date = new Date();
	date.setDate(date.getDate() - days);
	return date.toISOString().slice(0, 10);
}

export function InstrumentChartView({ id }: InstrumentChartViewProps) {
	const [startDate, setStartDate] = useState(() => dateDaysAgo(120));
	const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10));
	const query = useInstrumentChart(id, { endDate, startDate });

	return (
		<div className="p-[var(--density-panel-padding)]">
			<ContextSection title="日线证据">
				<div className="flex flex-wrap items-end justify-between gap-3 border-b border-(--color-border-subtle) p-3">
					<div className="flex flex-wrap gap-3">
						<label className="grid gap-1 text-xs text-(--color-foreground-tertiary)">
							开始日期
							<input
								type="date"
								value={startDate}
								onChange={(event) => setStartDate(event.currentTarget.value)}
								className="rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1.5 text-sm text-(--color-foreground)"
							/>
						</label>
						<label className="grid gap-1 text-xs text-(--color-foreground-tertiary)">
							截至日期
							<input
								type="date"
								value={endDate}
								onChange={(event) => setEndDate(event.currentTarget.value)}
								className="rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1.5 text-sm text-(--color-foreground)"
							/>
						</label>
					</div>
					<div className="max-w-lg text-right text-xs leading-5 text-(--color-foreground-tertiary)">
						复权：none · experimental：关闭
						<br />
						快照标识未由接口提供，仅作研究浏览，不生成交易建议
					</div>
				</div>

				{query.isLoading && <LoadingSkeleton variant="table" rows={8} />}
				{query.isError && <ErrorState onRetry={() => void query.refetch()} />}
				{query.data?.length === 0 && (
					<div className="p-10 text-center text-sm text-(--color-foreground-tertiary)">所选日期范围没有可见行情</div>
				)}
				{query.data && query.data.length > 0 && (
					<div className="overflow-x-auto p-3">
						<table className="w-full min-w-180 text-sm">
							<thead className="text-left text-xs text-(--color-foreground-tertiary)">
								<tr className="border-b border-(--color-border-primary)">
									{["交易日", "开", "高", "低", "收", "成交量", "成交额", "换手率"].map((label) => (
										<th key={label} className="px-2 py-2 font-medium">
											{label}
										</th>
									))}
								</tr>
							</thead>
							<tbody>
								{query.data.map((bar) => (
									<tr
										key={`${bar.instrument_id}-${bar.trade_date}`}
										className="border-b border-(--color-border-subtle) hover:bg-(--color-interaction-hover-subtle-bg)"
									>
										<td className="px-2 py-2 font-mono">{bar.trade_date}</td>
										<td className="px-2 py-2">{bar.open.toFixed(2)}</td>
										<td className="px-2 py-2">{bar.high.toFixed(2)}</td>
										<td className="px-2 py-2">{bar.low.toFixed(2)}</td>
										<td className="px-2 py-2 font-semibold">{bar.close.toFixed(2)}</td>
										<td className="px-2 py-2">{bar.volume.toLocaleString()}</td>
										<td className="px-2 py-2">{bar.amount.toLocaleString()}</td>
										<td className="px-2 py-2">
											{bar.turnover_rate == null ? "—" : `${bar.turnover_rate.toFixed(2)}%`}
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				)}
			</ContextSection>
		</div>
	);
}
