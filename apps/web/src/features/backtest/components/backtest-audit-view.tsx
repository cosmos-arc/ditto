import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import { useBacktestAudit } from "../hooks";

export function BacktestAuditView({ jobId }: { readonly jobId: string }) {
	const query = useBacktestAudit(jobId);
	if (query.isLoading) return <LoadingSkeleton variant="table" rows={6} />;
	if (query.error) {
		const message =
			query.error instanceof ApiError
				? `${query.error.status} ${query.error.errorCode ?? "BACKTEST_AUDIT_ERROR"}: ${query.error.message}`
				: query.error.message;
		return (
			<div className="rounded-(--radius-md) border border-(--color-led-danger) bg-(--color-surface-1) p-4 text-xs">
				<p role="alert" className="text-(--color-led-danger)">
					{message}
				</p>
				<Button size="sm" variant="outline" className="mt-3" onClick={() => void query.refetch()}>
					重试审计证据
				</Button>
			</div>
		);
	}
	const rows = query.data ?? [];
	return (
		<section className="overflow-hidden rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1)">
			<div className="grid grid-cols-[5rem_minmax(10rem,1fr)_8rem_10rem_minmax(10rem,1.2fr)] border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2 text-xs uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">
				<span>ID</span>
				<span>Record type</span>
				<span>Trade date</span>
				<span>Instrument</span>
				<span>Created / payload</span>
			</div>
			{rows.length === 0 ? (
				<p className="p-4 text-xs text-(--color-foreground-tertiary)">当前运行没有审计记录。</p>
			) : (
				<div className="divide-y divide-(--color-border-subtle)">
					{rows.map((row) => (
						<div
							key={row.id}
							className="grid grid-cols-[5rem_minmax(10rem,1fr)_8rem_10rem_minmax(10rem,1.2fr)] items-start px-3 py-3 text-xs"
						>
							<span className="font-data text-(--color-foreground-tertiary)">#{row.id}</span>
							<span className="font-data font-medium text-(--color-foreground)">{row.recordType}</span>
							<span className="font-data text-(--color-foreground-secondary)">{row.tradeDate || "—"}</span>
							<span className="font-data text-(--color-foreground-secondary)">
								{row.instrumentId === null ? "—" : `Instrument #${row.instrumentId}`}
							</span>
							<div className="min-w-0">
								<p className="font-data text-(--color-foreground-tertiary)">{row.createdAt || "—"}</p>
								<details className="mt-1">
									<summary className="cursor-pointer text-(--color-foreground-secondary)">查看载荷</summary>
									<pre className="mt-2 overflow-x-auto rounded-(--radius-sm) bg-(--color-surface-strip) p-2 text-xs">
										{JSON.stringify(row.payload, null, 2)}
									</pre>
								</details>
							</div>
						</div>
					))}
				</div>
			)}
		</section>
	);
}
