import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { ErrorState } from "@/lib/error-boundary";
import { useInstrumentDetail } from "../hooks";

interface InstrumentOverviewProps {
	readonly id: string;
}

export function InstrumentOverview({ id }: InstrumentOverviewProps) {
	const query = useInstrumentDetail(id);

	if (query.isError) return <ErrorState onRetry={() => void query.refetch()} />;

	const fields = query.data
		? ([
				["内部 ID", String(query.data.instrument_id)],
				["裸代码", query.data.ticker],
				["交易所", query.data.exchange],
				["资产类别", query.data.asset_class],
				["上市日期", query.data.list_date ?? "未报告"],
				["当前状态", query.data.is_active ? "交易中" : "非活跃"],
			] as const)
		: [];

	return (
		<div className="grid gap-[var(--section-gap)] p-[var(--density-panel-padding)] lg:grid-cols-[minmax(0,1.45fr)_minmax(280px,0.75fr)]">
			<div data-info-level="l2" data-info-unit="instrument-profile">
				<ContextSection title="标的档案">
					{query.isLoading ? (
						<LoadingSkeleton variant="table" rows={6} />
					) : (
						<dl className="grid gap-px overflow-hidden rounded-lg border border-(--color-border-subtle) bg-(--color-border-subtle) sm:grid-cols-2">
							{fields.map(([label, value]) => (
								<div
									key={label}
									data-info-level="l3"
									data-info-unit="instrument-profile-item"
									className="bg-(--color-surface-1) px-4 py-3"
								>
									<dt className="text-xs text-(--color-foreground-tertiary)">{label}</dt>
									<dd className="mt-1 font-medium text-sm text-(--color-foreground)">{value}</dd>
								</div>
							))}
						</dl>
					)}
				</ContextSection>
			</div>

			<div data-info-level="l2" data-info-unit="fundamental-boundary">
				<ContextSection title="基本面边界">
					<div className="rounded-lg border border-(--color-border-subtle) bg-(--color-surface-1) p-4 text-sm leading-6">
						<p className="font-medium text-(--color-foreground)">实验数据默认关闭</p>
						<p className="mt-1 text-(--color-foreground-tertiary)">
							财务、估值与分红接口需要精确 as-of 日期并显式允许 experimental 数据。本页不会用演示值填充
							PE、PB、行业或同业比较。
						</p>
					</div>
				</ContextSection>
			</div>
		</div>
	);
}
