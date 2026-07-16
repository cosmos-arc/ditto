import { ContextSection } from "@/components/domain/context-section";
import { ConfidenceBar, type Segment } from "@/components/indicator";

/** Mock data — will be replaced with real API hooks */
const STATUS_STATS = [
	{ label: "Agent Plans 今日", value: "5", sub: "运行中 2 · 完成 3", variant: "brand" as const },
	{ label: "Copilot 本周对话", value: "18", sub: "活跃 1 · 归档 17", variant: "default" as const },
	{ label: "待审批", value: "3", sub: "高 1 · 中 1 · 低 1", variant: "warning" as const },
] as const;

const CONFIDENCE_TIERS = [
	{ label: "高置信 (80-100)", count: 5, level: "high" as const },
	{ label: "中置信 (50-79)", count: 4, level: "medium" as const },
	{ label: "低置信 (0-49)", count: 3, level: "low" as const },
] as const;

const CONFIDENCE_SEGMENTS = [
	{ value: 42, color: "success", label: "高置信 42%" },
	{ value: 33, color: "warning", label: "中置信 33%" },
	{ value: 25, color: "danger", label: "低置信 25%" },
] as const satisfies readonly Segment[];

const ALERTS = [
	{ severity: "critical" as const, title: "情绪 Alpha v2 IC 持续衰减", time: "2小时" },
	{ severity: "warning" as const, title: "Tushare API 接近频率上限", time: "持续" },
] as const;

const RESOURCE_METRICS = [
	{ label: "API 调用", value: "4,820 / 5,000", variant: "warning" as const },
	{ label: "GPU 使用", value: "32%", variant: "default" as const },
	{ label: "Agent 并发", value: "2 / 4", variant: "brand" as const },
	{ label: "模型延迟", value: "180ms", variant: "default" as const },
] as const;

const ACTIVITIES = [
	{ status: "running" as const, title: "行业轮动扫描 — Q1 季报因子验证", time: "进行中 · 步骤 3/7" },
	{ status: "running" as const, title: "持仓集中度监控 — 每日巡检", time: "进行中 · 步骤 5/6" },
	{ status: "completed" as const, title: "价值因子 Q1 回测完成", time: "1小时前 · Sharpe 1.42" },
	{ status: "failed" as const, title: "期权波动率曲面校准失败", time: "5小时前 · API 超时" },
] as const;

const NAV_LINKS = [
	{ href: "/ai/agents", label: "Agent 管理中心" },
	{ href: "/ai/copilot", label: "Copilot 对话" },
	{ href: "/trading/signals", label: "待审批信号" },
	{ href: "/research/factors", label: "Factor Discovery" },
] as const;

const DOT_COLORS: Record<string, string> = {
	high: "bg-(--color-system-healthy-fg)",
	medium: "bg-(--color-system-degraded-fg)",
	low: "bg-(--color-risk-critical-fg)",
	critical: "bg-(--color-system-down-fg)",
	warning: "bg-(--color-system-degraded-fg)",
	brand: "text-(--color-accent)",
	default: "text-(--color-foreground)",
	warning_text: "text-(--color-system-degraded-fg)",
};

const VALUE_COLORS: Record<string, string> = {
	brand: "text-(--color-accent)",
	warning: "text-(--color-system-degraded-fg)",
	default: "text-(--color-foreground)",
};

export function AiContextSidebar() {
	return (
		<aside data-slot="sidebar-rail" data-testid="sidebar-rail" className="flex h-full flex-col overflow-y-auto">
			{/* AI 状态概览 */}
			<ContextSection title="AI 状态概览" data-info-level="l1" data-info-unit="ai-status-overview">
				<div className="space-y-2 py-1">
					{STATUS_STATS.map((stat) => (
						<div key={stat.label} className="rounded-md bg-(--color-surface-panel-base) px-3 py-2">
							<div className="text-xs text-(--color-foreground-tertiary)">{stat.label}</div>
							<div className="mt-0.5 flex items-baseline gap-2">
								<span className={`font-data text-sm font-semibold ${VALUE_COLORS[stat.variant]}`}>{stat.value}</span>
								<span className="text-xs text-(--color-foreground-tertiary)">{stat.sub}</span>
							</div>
						</div>
					))}
				</div>
			</ContextSection>

			{/* 置信度分布 */}
			<ContextSection title="置信度分布" data-info-level="l1" data-info-unit="ai-confidence-distribution">
				<div className="space-y-2 py-1">
					{CONFIDENCE_TIERS.map((tier) => (
						<div key={tier.level} className="flex items-center gap-2 text-xs">
							<span className={`size-2 rounded-full ${DOT_COLORS[tier.level]}`} />
							<span className="text-(--color-foreground-secondary)">{tier.label}</span>
							<span className="ml-auto font-data text-(--color-foreground-tertiary)">{tier.count}</span>
						</div>
					))}
					<ConfidenceBar value={100} segments={CONFIDENCE_SEGMENTS} aria-label="置信度分布" />
					<div className="flex text-xs text-(--color-foreground-tertiary)">
						<span className="flex-1">42%</span>
						<span className="flex-1">33%</span>
						<span className="flex-1">25%</span>
					</div>
				</div>
			</ContextSection>

			{/* AI 预警 */}
			<ContextSection title="AI 预警" count={2} data-info-level="l1" data-info-unit="ai-alerts">
				<div className="space-y-1.5 py-1">
					{ALERTS.map((alert) => (
						<div key={alert.title} className="flex items-start gap-2 text-xs">
							<span className={`mt-1 size-1.5 shrink-0 rounded-full ${DOT_COLORS[alert.severity]}`} />
							<span className="flex-1 text-(--color-foreground-secondary)">{alert.title}</span>
							<span className="shrink-0 text-(--color-foreground-tertiary)">{alert.time}</span>
						</div>
					))}
				</div>
			</ContextSection>

			{/* 资源用量 */}
			<ContextSection title="资源用量">
				<div className="space-y-2 py-1">
					{RESOURCE_METRICS.map((metric) => (
						<div key={metric.label} className="flex items-baseline justify-between text-xs">
							<span className="text-(--color-foreground-tertiary)">{metric.label}</span>
							<span className={`font-data ${VALUE_COLORS[metric.variant]}`}>{metric.value}</span>
						</div>
					))}
				</div>
			</ContextSection>

			{/* 活动轨迹 */}
			<ContextSection title="活动轨迹">
				<div className="space-y-1.5 py-1">
					{ACTIVITIES.map((activity) => (
						<div key={activity.title} className="text-xs">
							<div className="text-(--color-foreground-secondary)">{activity.title}</div>
							<div className="text-(--color-foreground-tertiary)">{activity.time}</div>
						</div>
					))}
				</div>
			</ContextSection>

			{/* 快捷导航 */}
			<ContextSection title="快捷导航">
				<div className="space-y-1 py-1">
					{NAV_LINKS.map((link) => (
						<a
							key={link.href}
							href={link.href}
							className="flex items-center gap-1.5 rounded-sm px-1 py-1 text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) hover:text-(--color-foreground)"
						>
							<span className="text-(--color-accent)">→</span>
							<span>{link.href}</span>
							<span className="text-(--color-foreground-tertiary)">—</span>
							<span>{link.label}</span>
						</a>
					))}
				</div>
			</ContextSection>
		</aside>
	);
}
