import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";

const MOCK_CONTEXT_ITEMS = [
	{ label: "当前组合", value: "主策略组合" },
	{ label: "持仓数量", value: "23 只" },
	{ label: "现金比例", value: "8.2%" },
];

export function CopilotContextPanel() {
	return (
		<Panel>
			<PanelHeader title="会话上下文" />
			<PanelBody className="p-3">
				<div className="space-y-2">
					{MOCK_CONTEXT_ITEMS.map((item) => (
						<div
							key={item.label}
							className="flex items-center justify-between text-xs"
						>
							<span className="text-(--color-foreground-tertiary)">{item.label}</span>
							<span className="font-medium text-(--color-foreground-secondary)">{item.value}</span>
						</div>
					))}
				</div>
			</PanelBody>
		</Panel>
	);
}
