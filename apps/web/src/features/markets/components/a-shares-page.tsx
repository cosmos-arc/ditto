import { useState } from "react";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { AnalyticalLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import { ASharesOverview } from "./a-shares-overview";
import { ASharesOverlay, type ASharesOverlayId, aSharesActions } from "./market-page-overlays";
import type { MarketCatalogQuery } from "./market-view-contracts";

export function ASharesPage({ catalog }: { readonly catalog: MarketCatalogQuery }) {
	const [activeOverlay, setActiveOverlay] = useState<ASharesOverlayId | null>(null);
	return (
		<>
			<AnalyticalLayout
				strip={
					<div className="flex flex-wrap items-center gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2">
						<div className="min-w-0 flex-1">
							<p className="text-sm font-medium">A 股市场</p>
							<p className="text-xs text-(--color-foreground-tertiary)">范围：active stock metadata · 价格快照未加载</p>
						</div>
						<PageActionBar ariaLabel="A 股页面操作" actions={aSharesActions} onOpen={setActiveOverlay} />
					</div>
				}
				main={
					<div
						data-info-level="l1"
						data-info-unit="a-shares-main"
						className="h-full overflow-y-auto p-(--density-panel-padding)"
					>
						<ASharesOverview query={catalog} />
					</div>
				}
				activity={
					<Panel data-info-level="l1" data-info-unit="market-evidence-boundary">
						<PanelHeader title="证据边界" />
						<PanelBody className="p-4 text-sm leading-6 text-(--color-foreground-secondary)">
							<p className="font-medium text-(--color-foreground)">价格与涨跌未查询</p>
							<p className="mt-1">
								metadata 合同只回答标的身份、上市日期与活跃状态。没有 immutable snapshot identity
								时，本页不展示收盘点位、成交额或涨跌比。
							</p>
						</PanelBody>
					</Panel>
				}
			/>
			<ASharesOverlay active={activeOverlay} onClose={() => setActiveOverlay(null)} />
		</>
	);
}
