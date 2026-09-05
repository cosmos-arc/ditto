import { OverlayFactList, PageActionOverlay } from "@/components/domain/page-action-overlay";
import { Button } from "@/components/ui/button";

export type SystemOverlayId = "pipeline-rerun" | "alert-handle" | "task-detail";

export const systemActions = [
	{ id: "pipeline-rerun", label: "Pipeline 重跑" },
	{ id: "alert-handle", label: "处理异常" },
	{ id: "task-detail", label: "任务详情" },
] as const;

const systemCopy = {
	"pipeline-rerun": {
		title: "Pipeline 重跑确认",
		description: "当前产品只公开运行证据读取，没有任务重跑 command。",
		kind: "modal",
	},
	"alert-handle": {
		title: "异常处理",
		description: "查看阻塞原因与建议动作；处理结果不会旁路写入。",
		kind: "alert-dialog",
	},
	"task-detail": {
		title: "任务详情",
		description: "来自当前交易日 remediation projection 的首个待办。",
		kind: "drawer",
	},
} as const;

export function SystemOverlays({
	active,
	datasetId,
	onClose,
	onRefresh,
	reasons,
	suggestedActions,
	tradeDate,
}: {
	readonly active: SystemOverlayId | null;
	readonly datasetId: string;
	readonly onClose: () => void;
	readonly onRefresh: () => void;
	readonly reasons: string;
	readonly suggestedActions: string;
	readonly tradeDate: string;
}) {
	if (!active) return null;
	const details = systemCopy[active];
	return (
		<PageActionOverlay
			{...details}
			open
			onClose={onClose}
			actions={
				active === "pipeline-rerun" ? (
					<Button
						type="button"
						onClick={() => {
							onRefresh();
							onClose();
						}}
					>
						重新读取证据（不重跑）
					</Button>
				) : undefined
			}
		>
			<OverlayFactList
				facts={[
					["交易日", tradeDate],
					["Dataset", datasetId || "当前无待办"],
					["阻塞原因", reasons || "未报告"],
					["建议动作", suggestedActions || "人工复核"],
				]}
			/>
			<p className="rounded-(--radius-md) border border-(--color-risk-warning)/40 bg-(--color-risk-warning)/5 p-3 text-xs leading-5 text-(--color-risk-warning-fg)">
				没有公共 command 时，界面保持只读并明确阻断，不把 refetch 冒充重跑或异常已处理。
			</p>
		</PageActionOverlay>
	);
}

export type SystemSettingsOverlayId = "datasource-test" | "save-config" | "reset-config";

export const systemSettingsActions = [
	{ id: "datasource-test", label: "测试数据源" },
	{ id: "save-config", label: "保存配置" },
	{ id: "reset-config", label: "重置配置" },
] as const;

const settingsCopy = {
	"datasource-test": {
		title: "数据源连接测试",
		description: "通过重新读取 Catalog 证据验证当前公开数据面。",
		kind: "sheet",
	},
	"save-config": { title: "保存配置确认", description: "当前 API 没有配置写入 command。", kind: "modal" },
	"reset-config": { title: "重置配置确认", description: "当前 API 没有配置重置或回滚 command。", kind: "alert-dialog" },
} as const;

export function SystemSettingsOverlays({
	active,
	agentState,
	assetCount,
	onClose,
	onRefresh,
	runtimeState,
}: {
	readonly active: SystemSettingsOverlayId | null;
	readonly agentState: string;
	readonly assetCount: number;
	readonly onClose: () => void;
	readonly onRefresh: () => void;
	readonly runtimeState: string;
}) {
	if (!active) return null;
	const details = settingsCopy[active];
	return (
		<PageActionOverlay
			{...details}
			open
			onClose={onClose}
			actions={
				active === "datasource-test" ? (
					<Button
						type="button"
						onClick={() => {
							onRefresh();
							onClose();
						}}
					>
						重新读取 Catalog
					</Button>
				) : undefined
			}
		>
			<OverlayFactList
				facts={[
					["Runtime", runtimeState],
					["Catalog assets", String(assetCount)],
					["Agent", agentState],
					["Account modes", "Manual / Paper"],
				]}
			/>
			<p className="rounded-(--radius-md) border border-(--color-risk-warning)/40 bg-(--color-risk-warning)/5 p-3 text-xs leading-5 text-(--color-risk-warning-fg)">
				{active === "datasource-test"
					? "测试只重新读取服务端公开证据，不显示或修改 secret。"
					: "操作被公共 API 边界阻断；没有写入或虚假成功状态。"}
			</p>
		</PageActionOverlay>
	);
}
