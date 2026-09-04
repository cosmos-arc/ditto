import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { DataProductView } from "../api";

interface DataProductOverviewProps {
	readonly product: DataProductView;
	readonly certifiedCount: number;
	readonly totalCount: number;
}

function maturityLabel(maturity: string): string {
	if (maturity === "initial-focus") return "Initial focus";
	if (maturity === "experimental") return "Experimental";
	return maturity;
}

export function DataProductOverview({ product, certifiedCount, totalCount }: DataProductOverviewProps) {
	const certificationState = product.active_certification_report_id ? "已认证" : "待认证";
	const bundleReadiness = certifiedCount === totalCount && totalCount === 19 ? "ready" : "blocked";
	return (
		<Panel className="h-full" data-info-level="l1" data-info-unit="data-product-overview">
			<PanelHeader title="产品概览" subtitle={product.dataset_id} />
			<PanelBody className="p-(--density-panel-padding)">
				<div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(12rem,0.65fr)]">
					<section aria-label="当前产品状态">
						<p className="text-xs font-medium text-(--color-foreground-tertiary)">当前判断</p>
						<div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
							<strong className="text-lg font-semibold text-(--color-foreground)">{certificationState}</strong>
							<span className="font-data text-xs text-(--color-foreground-secondary)">
								{maturityLabel(product.maturity)}
							</span>
						</div>
						<p className="mt-2 max-w-[68ch] text-sm text-(--color-foreground-secondary)">
							{product.active_certification_report_id
								? "存在已审批的不可变认证报告，可继续核对 coverage、quality 与许可证据。"
								: "尚无 active certification，策略消费保持 fail closed。"}
						</p>
					</section>
					<section
						aria-label="R2 认证进度"
						className="border-t border-(--color-border-subtle) pt-3 md:border-t-0 md:border-l md:pt-0 md:pl-4"
					>
						<p className="text-xs text-(--color-foreground-tertiary)">R2 认证进度</p>
						<p className="mt-1 font-data text-lg tabular-nums text-(--color-foreground)">
							{certifiedCount} / {totalCount}
						</p>
						<p
							className={
								bundleReadiness === "ready"
									? "mt-1 text-xs font-medium text-(--color-system-healthy-fg)"
									: "mt-1 text-xs font-medium text-(--color-system-degraded-fg)"
							}
						>
							Bundle readiness: {bundleReadiness}
						</p>
						<p className="mt-1 text-xs text-(--color-foreground-secondary)">
							每个 dataset 独立认证，bundle 不替代产品证据。
						</p>
					</section>
				</div>
				<dl className="mt-5 grid gap-x-4 gap-y-3 border-t border-(--color-border-subtle) pt-4 sm:grid-cols-2 xl:grid-cols-3">
					<div>
						<dt className="text-xs text-(--color-foreground-tertiary)">Owner</dt>
						<dd className="mt-1 text-sm text-(--color-foreground)">{product.owner}</dd>
					</div>
					<div>
						<dt className="text-xs text-(--color-foreground-tertiary)">Schedule</dt>
						<dd className="mt-1 font-data text-sm text-(--color-foreground)">{product.schedule}</dd>
					</div>
					<div>
						<dt className="text-xs text-(--color-foreground-tertiary)">Frequency</dt>
						<dd className="mt-1 font-data text-sm text-(--color-foreground)">{product.frequency}</dd>
					</div>
					<div>
						<dt className="text-xs text-(--color-foreground-tertiary)">Schema</dt>
						<dd className="mt-1 break-all font-code text-xs text-(--color-foreground)">{product.schema_version}</dd>
					</div>
					<div>
						<dt className="text-xs text-(--color-foreground-tertiary)">Timezone / Currency</dt>
						<dd className="mt-1 font-data text-sm text-(--color-foreground)">
							{product.timezone} · {product.currency ?? "N/A"}
						</dd>
					</div>
					<div>
						<dt className="text-xs text-(--color-foreground-tertiary)">R2 scope</dt>
						<dd className="mt-1 font-data text-sm text-(--color-foreground)">{product.r2_scope}</dd>
					</div>
					<div>
						<dt className="text-xs text-(--color-foreground-tertiary)">Raw target</dt>
						<dd className="mt-1 font-data text-sm text-(--color-foreground)">{product.raw_target_from ?? "未声明"}</dd>
					</div>
					<div>
						<dt className="text-xs text-(--color-foreground-tertiary)">Certified target</dt>
						<dd className="mt-1 font-data text-sm text-(--color-foreground)">
							{product.certified_target_from ?? "未声明"}
						</dd>
					</div>
					<div>
						<dt className="text-xs text-(--color-foreground-tertiary)">Active report</dt>
						<dd className="mt-1 break-all font-code text-xs text-(--color-foreground)">
							{product.active_certification_report_id ?? "none"}
						</dd>
					</div>
				</dl>
			</PanelBody>
		</Panel>
	);
}
