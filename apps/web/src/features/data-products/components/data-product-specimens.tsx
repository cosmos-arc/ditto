import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { DataSpecimenCategory } from "../api";

const CATEGORY_LABELS: Record<string, string> = {
	financial_restatement: "财报重述",
	delisted_security: "退市证券",
	index_rebalance: "指数调样",
	dividend_etf: "分红 ETF",
	cross_border_etf: "跨境 ETF",
};

const USE_LABELS: Record<string, string> = {
	display: "展示",
	exploration: "探索",
	formal_research: "正式研究",
	promotion_paper: "晋级/Paper",
};

function categoryLabel(category: string): string {
	return CATEGORY_LABELS[category] ?? category;
}

function formatUses(uses: readonly string[]): string {
	return uses.map((use) => USE_LABELS[use] ?? use).join("、");
}

interface DataProductSpecimensProps {
	readonly categories: readonly DataSpecimenCategory[] | undefined;
	readonly isLoading: boolean;
	readonly isError: boolean;
}

export function DataProductSpecimens({ categories, isLoading, isError }: DataProductSpecimensProps) {
	if (isError) {
		return (
			<Panel className="h-full">
				<PanelHeader title="五类数据试样" />
				<PanelBody className="p-4">
					<p role="alert" className="text-sm text-(--color-risk-critical-fg)">
						试样 API 不可用，结论保持未知，不以空数据伪造就绪。
					</p>
				</PanelBody>
			</Panel>
		);
	}
	if (isLoading || !categories) {
		return (
			<Panel className="h-full">
				<PanelHeader title="正在加载五类试样" />
				<PanelBody className="space-y-2 p-3">
					{["one", "two", "three", "four", "five"].map((key) => (
						<div key={key} className="h-8 animate-pulse rounded-(--radius-sm) bg-(--color-surface-muted)" />
					))}
				</PanelBody>
			</Panel>
		);
	}
	return (
		<Panel className="h-full">
			<PanelHeader title="五类数据试样" subtitle="逐项留证；缺试样保持未验证，不伪造通过" count={categories.length} />
			<PanelBody>
				<div className="overflow-x-auto">
					<table aria-label="五类数据试样结论" className="w-full min-w-[44rem] text-left text-xs">
						<thead className="sticky top-0 z-10 bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
							<tr>
								<th className="px-3 py-2 font-medium">类别</th>
								<th className="px-3 py-2 font-medium">状态</th>
								<th className="px-3 py-2 font-medium">锚定标的</th>
								<th className="px-3 py-2 font-medium">允许用途</th>
								<th className="px-3 py-2 font-medium">上游独立</th>
								<th className="px-3 py-2 font-medium">缺口</th>
							</tr>
						</thead>
						<tbody className="divide-y divide-(--color-border-subtle)">
							{categories.map((category) => {
								const latest = category.latest;
								const verified = latest?.verification_status === "verified";
								return (
									<tr key={category.category} data-category={category.category}>
										<td className="px-3 py-1.5 font-medium">{categoryLabel(category.category)}</td>
										<td
											className={
												verified
													? "px-3 py-1.5 font-medium text-(--color-system-healthy-fg)"
													: "px-3 py-1.5 font-medium text-(--color-system-degraded-fg)"
											}
										>
											{verified ? "✓ 已验证" : "○ 未验证"}
										</td>
										<td className="px-3 py-1.5 font-code text-(--color-foreground-secondary)">
											{latest?.anchor ?? "—"}
										</td>
										<td className="px-3 py-1.5 text-(--color-foreground-secondary)">
											{latest ? formatUses(latest.allowed_uses) : "—"}
										</td>
										<td className="px-3 py-1.5 text-(--color-foreground-secondary)">
											{latest ? (latest.upstream_independent ? "是" : "否/未知") : "—"}
										</td>
										<td className="px-3 py-1.5 font-data text-(--color-foreground-tertiary)">
											{category.unresolved_gaps.length > 0 ? category.unresolved_gaps.join("、") : "—"}
										</td>
									</tr>
								);
							})}
						</tbody>
					</table>
				</div>
			</PanelBody>
		</Panel>
	);
}
