import { useState } from "react";
import { AgentQuickView } from "./agent-quick-view";
import { CopilotQuickView } from "./copilot-quick-view";

type TabId = "overview" | "agents" | "copilot" | "settings";

const TABS: readonly { id: TabId; label: string }[] = [
	{ id: "overview", label: "Overview" },
	{ id: "agents", label: "Agents" },
	{ id: "copilot", label: "Copilot" },
	{ id: "settings", label: "Settings" },
] as const;

const ACTIONS = [
	{ label: "新建计划", href: "/ai/agents" },
	{ label: "审批队列", href: "/trading/signals" },
	{ label: "开始会话", href: "/ai/copilot" },
] as const;

export function AiMainContent() {
	const [activeTab, setActiveTab] = useState<TabId>("overview");

	return (
		<div className="flex h-full flex-col">
			{/* Tab navigation */}
			<nav
				className="flex shrink-0 items-center gap-1 border-b border-(--color-border-subtle) px-4 py-2"
				aria-label="AI Overview tabs"
			>
				{TABS.map((tab) => (
					<button
						key={tab.id}
						type="button"
						role="tab"
						aria-selected={activeTab === tab.id}
						onClick={() => setActiveTab(tab.id)}
						className={[
							"rounded-sm px-3 py-1 text-xs font-medium transition-colors",
							activeTab === tab.id
								? "bg-(--color-surface-2) text-(--color-foreground)"
								: "text-(--color-foreground-tertiary) hover:text-(--color-foreground-secondary)",
						].join(" ")}
					>
						{tab.label}
					</button>
				))}
			</nav>

			{/* Tab panels */}
			<div className="min-h-0 flex-1 overflow-y-auto p-4">
				{activeTab === "overview" && <OverviewPanel />}
				{activeTab === "agents" && <AgentsPanel />}
				{activeTab === "copilot" && <CopilotPanel />}
				{activeTab === "settings" && <SettingsPanel />}
			</div>

			{/* Actions bar */}
			{activeTab === "overview" && (
				<div className="grid shrink-0 grid-cols-3 gap-3 border-t border-(--color-border-subtle) p-4">
					{ACTIONS.map((action) => (
						<a
							key={action.label}
							href={action.href}
							className="flex items-center justify-center rounded-md border border-(--color-border-subtle) bg-(--color-surface-panel-base) px-3 py-2 text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) hover:text-(--color-foreground)"
						>
							{action.label}
						</a>
					))}
				</div>
			)}
		</div>
	);
}

function OverviewPanel() {
	return (
		<div data-info-level="l1" data-info-unit="ai-overview" className="grid grid-cols-2 gap-4">
			<AgentQuickView />
			<CopilotQuickView />
		</div>
	);
}

function AgentsPanel() {
	return (
		<div data-info-level="l1" data-info-unit="ai-agents" className="flex flex-col gap-3">
			<p className="text-sm text-(--color-foreground-secondary)">
				查看和管理所有 Agent 计划的运行状态、发现和审批流程。
			</p>
			<a
				href="/ai/agents"
				className="inline-flex items-center gap-1 text-xs text-(--color-accent) hover:underline"
			>
				进入 Agent 管理中心 →
			</a>
		</div>
	);
}

function CopilotPanel() {
	return (
		<div data-info-level="l1" data-info-unit="ai-copilot" className="flex flex-col gap-3">
			<p className="text-sm text-(--color-foreground-secondary)">
				查看和继续 Copilot 研究对话、交易分析和代码辅助会话。
			</p>
			<a
				href="/ai/copilot"
				className="inline-flex items-center gap-1 text-xs text-(--color-accent) hover:underline"
			>
				进入 Copilot 对话 →
			</a>
		</div>
	);
}

function SettingsPanel() {
	return (
		<div data-info-level="l1" data-info-unit="ai-settings" className="flex flex-col gap-3">
			<p className="text-sm text-(--color-foreground-secondary)">
				配置 AI Agent 和 Copilot 的运行参数、模型偏好和资源限制。
			</p>
		</div>
	);
}
