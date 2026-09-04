import { OverlayFactList, PageActionOverlay } from "@/components/domain/page-action-overlay";
import { Button } from "@/components/ui/button";

export type ScreenerOverlayId = "save-preset" | "column-manage" | "compare" | "generate-pool" | "export";

export const screenerActions = [
	{ id: "save-preset", label: "保存预设" },
	{ id: "column-manage", label: "列管理" },
	{ id: "compare", label: "打开对比" },
	{ id: "generate-pool", label: "生成标的池" },
	{ id: "export", label: "导出结果" },
] as const;

const copy = {
	"save-preset": { title: "保存筛选预设", description: "预设只保存在当前浏览器，不写入服务端。", kind: "sheet" },
	"column-manage": { title: "列管理", description: "公开 metadata 字段是当前可用列的事实源。", kind: "sheet" },
	compare: { title: "身份对比", description: "只比较已选择标的的身份字段。", kind: "drawer" },
	"generate-pool": { title: "生成标的池", description: "确认候选范围后进入受控股票池创建流程。", kind: "modal" },
	export: { title: "导出筛选结果", description: "导出当前筛选后的 metadata CSV。", kind: "sheet" },
} as const;

export function ScreenerOverlays({
	active,
	filterSummary,
	onClose,
	onExport,
	onSavePreset,
	resultCount,
	selectedCount,
}: {
	readonly active: ScreenerOverlayId | null;
	readonly filterSummary: string;
	readonly onClose: () => void;
	readonly onExport: () => void;
	readonly onSavePreset: () => void;
	readonly resultCount: number;
	readonly selectedCount: number;
}) {
	if (!active) return null;
	const details = copy[active];
	const primaryAction =
		active === "save-preset" ? (
			<Button type="button" onClick={onSavePreset}>
				保存到本机
			</Button>
		) : active === "export" ? (
			<Button type="button" onClick={onExport} disabled={resultCount === 0}>
				下载 CSV
			</Button>
		) : active === "generate-pool" ? (
			<a
				className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-xs font-medium text-(--brand-accent-fg)"
				href="/research/universes"
			>
				前往股票池
			</a>
		) : undefined;

	return (
		<PageActionOverlay {...details} open onClose={onClose} actions={primaryAction}>
			<OverlayFactList
				facts={[
					["筛选", filterSummary],
					["结果", `${resultCount} 个身份`],
					["已选择", `${selectedCount} 个身份`],
					["价格/估值", "未查询"],
				]}
			/>
			{active === "column-manage" && (
				<ul className="grid grid-cols-2 gap-2 text-xs">
					{["名称", "代码", "资产类别", "交易所", "活跃状态"].map((column) => (
						<li key={column} className="rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-2">
							{column} · 固定
						</li>
					))}
				</ul>
			)}
			{active === "generate-pool" && (
				<p className="rounded-(--radius-md) border border-(--color-risk-warning)/40 bg-(--color-risk-warning)/5 p-3 text-xs text-(--color-risk-warning-fg)">
					本页不会旁路创建股票池；目标页面将再次确认定义与生效日期。
				</p>
			)}
		</PageActionOverlay>
	);
}
