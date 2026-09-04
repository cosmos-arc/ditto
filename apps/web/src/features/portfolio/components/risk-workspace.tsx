import { useState } from "react";
import { Drawer } from "@/components/indicator/overlay/drawer";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { AnalyticalLayout, ShellHeaderExtension, StatusBar } from "@/features/shell";
import { BreachDetailContent } from "./risk-breach-detail";

type RiskTab = "overview" | "stress" | "incidents";

const STRIP_METRICS = [
	["最大回撤距阈值 1.55pp，先降低科技集中度", "✓ 1.23%", "healthy"],
	["最大回撤", "! 接近 3.45%", "warning"],
	["Beta", "中性 0.87", "neutral"],
	["总仓位", "✓ 72.3%", "healthy"],
	["净敞口", "中性 45.1%", "neutral"],
	["执行降险动作", "! 2", "warning"],
	["突破数", "✓ 0", "healthy"],
	["夏普比率", "✓ 1.42", "healthy"],
] as const;

const RISK_EVENTS = [
	["09:32", "最大回撤接近阈值", "当前回撤 3.45%，距阈值 5% 仅剩 1.55 个百分点。建议关注持仓结构。", "监控中"],
	["08:45", "压力测试完成", "极端下跌和利率上行场景均通过，流动性危机场景突破风控线。", "已处理"],
	["14:22", "科技行业集中度预警", "科技行业持仓占比达 32.1%，接近阈值 40%。建议分散配置。", "监控中"],
	["前日", "日内 VaR 超限触发", "昨日 14:08 VaR(95%) 短暂触及 2.53%，超过阈值 2.50%，随后回落。已自动记录。", "已处理"],
	["3天前", "风控规则更新", "Beta 限制从 1.2 调整为 1.1；新增行业集中度预警规则。所有规则已生效。", "已处理"],
] as const;

const RISK_HEATMAP_CELLS = [
	"r1c1",
	"r1c2",
	"r1c3",
	"r1c4",
	"r1c5",
	"r1c6",
	"r2c1",
	"r2c2",
	"r2c3",
	"r2c4",
	"r2c5",
	"r2c6",
	"r3c1",
	"r3c2",
	"r3c3",
	"r3c4",
	"r3c5",
	"r3c6",
	"r4c1",
	"r4c2",
	"r4c3",
	"r4c4",
	"r4c5",
	"r4c6",
] as const;

const RISK_SERIES = {
	"VaR 趋势":
		"M0.00 84.00 L4.35 79.57 L8.70 81.79 L13.04 75.14 L17.39 67.39 L21.74 70.71 L26.09 64.07 L30.43 59.64 L34.78 65.18 L39.13 55.21 L43.48 58.54 L47.83 51.89 L52.17 45.25 L56.52 47.46 L60.87 41.93 L65.22 37.50 L69.57 33.07 L73.91 38.61 L78.26 26.43 L82.61 22.00 L86.96 28.64 L91.30 31.96 L95.65 39.71 L100.00 47.46",
	最大回撤:
		"M0.00 84.00 L4.35 75.55 L8.70 81.18 L13.04 69.91 L17.39 61.45 L21.74 55.82 L26.09 64.27 L30.43 47.36 L34.78 41.73 L39.13 50.18 L43.48 36.09 L47.83 30.45 L52.17 38.91 L56.52 27.64 L60.87 22.00 L65.22 26.23 L69.57 33.27 L73.91 36.09 L78.26 29.05 L82.61 22.56 L86.96 27.07 L91.30 30.45 L95.65 33.27 L100.00 36.09",
	行业暴露度:
		"M0.00 84.00 L4.35 74.21 L8.70 67.68 L13.04 61.16 L17.39 54.63 L21.74 51.37 L26.09 48.11 L30.43 41.58 L34.78 38.32 L39.13 35.05 L43.48 31.79 L47.83 25.26 L52.17 28.53 L56.52 22.00 L60.87 24.61 L65.22 28.53 L69.57 31.79 L73.91 35.05 L78.26 38.32 L82.61 41.58 L86.96 48.11 L91.30 51.37 L95.65 54.63 L100.00 57.89",
} as const;

function RiskPrimaryStrip() {
	return (
		<div
			data-info-level="l1"
			data-info-unit="risk-primary-strip"
			data-testid="risk-primary-strip"
			className="flex h-9 items-center gap-3 overflow-hidden border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4"
		>
			{STRIP_METRICS.map(([label, value, tone], index) => (
				<div key={label} className="contents">
					{index > 0 && <span aria-hidden="true" className="h-3.5 w-px shrink-0 bg-(--color-border-subtle)" />}
					<div className="flex h-6 shrink-0 items-center gap-1.5 whitespace-nowrap">
						<span className="text-xs leading-[1.35] font-semibold text-(--color-foreground-tertiary)">{label}</span>
						<span
							className={`font-data text-[12px] leading-[1.35] font-semibold ${tone === "healthy" ? "text-(--color-status-healthy-fg)" : tone === "warning" ? "text-(--color-risk-high-fg)" : "text-(--color-foreground-secondary)"}`}
						>
							{value}
						</span>
					</div>
				</div>
			))}
		</div>
	);
}

function RiskGauge({
	value,
	label,
	detail,
}: {
	readonly value: number;
	readonly label: string;
	readonly detail: string;
}) {
	const radius = 32.4;
	const circumference = 2 * Math.PI * radius;
	const offset = circumference * (1 - value / 100);
	return (
		<div className="flex items-center gap-2.5">
			<div className="relative size-[72px] shrink-0">
				<svg viewBox="0 0 72 72" className="-rotate-90" aria-hidden="true">
					<circle cx="36" cy="36" r={radius} fill="none" stroke="oklch(1 0 0 / 0.06)" strokeWidth="7.2" />
					<circle
						cx="36"
						cy="36"
						r={radius}
						fill="none"
						stroke="oklch(0.64 0.12 235)"
						strokeWidth="7.2"
						strokeLinecap="round"
						strokeDasharray={circumference}
						strokeDashoffset={offset}
					/>
				</svg>
				<span className="absolute inset-0 flex items-center justify-center font-data text-[14.4px] leading-[21.6px]">
					{value}%
				</span>
			</div>
			<div>
				<p className="text-sm leading-[18px] font-medium">{label}</p>
				<p className="mt-px text-xs leading-[15px] text-(--color-foreground-tertiary)">{detail}</p>
			</div>
		</div>
	);
}

function RiskGaugeBand() {
	return (
		<section
			data-info-level="l1"
			data-info-unit="risk-gauges"
			className="flex h-[97px] items-center gap-4 border-b border-(--color-border-subtle) px-4 py-3"
			aria-label="风险仪表"
		>
			<RiskGauge value={68} label="风险利用率" detail="VaR 额度已用 68%" />
			<RiskGauge value={49} label="VaR 占比" detail="占阈值 2.50% 的 49.2%" />
			<RiskGauge value={80} label="行业集中度" detail="科技行业 32.1% / 40%" />
		</section>
	);
}

function RiskTabBar({ tab, onChange }: { readonly tab: RiskTab; readonly onChange: (tab: RiskTab) => void }) {
	const tabs = [
		["overview", "风险概览"],
		["stress", "压力测试"],
		["incidents", "事件记录"],
	] as const;
	return (
		<div
			className="flex h-[37px] items-end gap-1 border-b border-(--color-border-subtle) px-4"
			role="tablist"
			aria-label="风险视图"
		>
			{tabs.map(([id, label]) => (
				<button
					key={id}
					type="button"
					role="tab"
					aria-selected={tab === id}
					onClick={() => onChange(id)}
					className={`h-9 border-b-2 px-3 text-xs ${tab === id ? "border-(--color-accent) text-(--color-accent)" : "border-transparent text-(--color-foreground-tertiary) hover:text-(--color-foreground)"}`}
				>
					{label}
				</button>
			))}
		</div>
	);
}

function RiskChart({ title, subtitle }: { readonly title: keyof typeof RISK_SERIES; readonly subtitle: string }) {
	const series = RISK_SERIES[title];
	const actions = title === "行业暴露度" ? ["饼图", "条形图"] : ["1W", "1M", "3M", "1Y"];
	return (
		<section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[8px] border border-(--color-border-subtle) bg-(--color-surface-panel-base)">
			<header className="flex h-[43px] shrink-0 items-center border-b border-(--color-border-subtle) px-3">
				<h3 className="text-base font-semibold text-(--color-foreground-secondary)">{title}</h3>
				<span className="ml-auto text-[12px] text-(--color-foreground-tertiary)">{subtitle}</span>
				<div className="ml-3 flex items-center gap-1 text-[12px] text-(--color-foreground-tertiary)">
					{actions.map((action) => (
						<span
							key={action}
							className={
								action === "1M" || action === "条形图"
									? "rounded bg-(--color-surface-panel-elevated) px-1.5 py-1 text-(--color-foreground)"
									: "px-1"
							}
						>
							{action}
						</span>
					))}
				</div>
			</header>
			<div
				className="relative min-h-[60px] flex-1 overflow-hidden rounded-b-[8px] border border-(--color-border-subtle) bg-(--color-surface-app)"
				role="img"
				aria-label={`${title}图`}
			>
				<svg
					viewBox="0 0 100 100"
					preserveAspectRatio="none"
					className="absolute inset-x-3 top-2 bottom-[34px] h-[calc(100%-42px)] w-[calc(100%-24px)] opacity-[0.86]"
					aria-hidden="true"
				>
					{[18, 38, 58, 78].map((y) => (
						<line
							key={y}
							x1="0"
							x2="100"
							y1={y}
							y2={y}
							stroke="var(--color-border-subtle)"
							opacity="0.45"
							vectorEffect="non-scaling-stroke"
						/>
					))}
					<line
						x1="0"
						x2="100"
						y1="34"
						y2="34"
						stroke="var(--color-risk-medium-fg)"
						strokeDasharray="3 3"
						opacity="0.5"
						vectorEffect="non-scaling-stroke"
					/>
					<path d={`${series} L 100 100 L 0 100 Z`} fill="oklch(0.76 0.055 74 / 0.08)" opacity="0.9" />
					<path
						d={series}
						fill="none"
						stroke="oklch(0.76 0.055 74)"
						strokeWidth="2"
						vectorEffect="non-scaling-stroke"
					/>
				</svg>
				<span className="absolute bottom-2 left-2 rounded border border-(--color-border-subtle) bg-[color-mix(in_oklch,var(--color-surface-app)_85%,transparent)] px-1.5 py-0.5 font-data text-xs leading-[inherit] text-(--color-foreground-tertiary)">
					1M · 2026-03-24
				</span>
				<fieldset className="absolute right-2 bottom-2 flex h-7 gap-1 border-0 p-0" aria-label="只读图表动作">
					{["建提醒", "发研究", "对比", "查回撤"].map((action) => (
						<span
							key={action}
							className="flex items-center rounded border border-(--color-border-strong) bg-[color-mix(in_oklch,var(--color-surface-app)_85%,transparent)] px-1.5 text-xs leading-[inherit] text-(--color-foreground-tertiary)"
						>
							{action}
						</span>
					))}
				</fieldset>
			</div>
		</section>
	);
}

function RiskOverviewDashboard() {
	return (
		<main
			data-info-level="l1"
			data-info-unit="risk-dashboard"
			data-testid="risk-dashboard"
			className="flex h-full min-h-0 flex-col gap-4 overflow-hidden"
		>
			<RiskChart title="VaR 趋势" subtitle="95% 置信区间 · 日线" />
			<RiskChart title="最大回撤" subtitle="当前 3.45% / 阈值 5.00%" />
			<RiskChart title="行业暴露度" subtitle="按中信一级行业分布" />
		</main>
	);
}

function RiskStressDashboard({ onOpenEvidence }: { readonly onOpenEvidence: () => void }) {
	const scenarios = [
		["沪深 300 -8%", "-5.42%", "通过"],
		["利率 +75bp", "-1.18%", "通过"],
		["科技板块 -12%", "-7.86%", "需复核"],
		["流动性收缩", "不可用", "source snapshot missing"],
	] as const;
	return (
		<main
			data-info-level="l1"
			data-info-unit="risk-dashboard"
			data-testid="risk-dashboard"
			className="h-full overflow-auto"
		>
			<div className="mb-3 flex items-center justify-between">
				<div>
					<h2 className="text-sm font-medium">压力场景损失</h2>
					<p className="mt-1 text-xs text-(--color-foreground-tertiary)">只展示后端已生成的场景证据</p>
				</div>
				<Button type="button" variant="outline" size="sm" onClick={onOpenEvidence}>
					查看压力测试证据
				</Button>
			</div>
			<div className="grid grid-cols-2 gap-3">
				{scenarios.map(([name, loss, status]) => (
					<div
						key={name}
						className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-4"
					>
						<div className="flex items-center justify-between">
							<span className="text-sm">{name}</span>
							<span
								className={`text-xs ${status === "通过" ? "text-(--color-status-healthy-fg)" : "text-(--color-risk-high-fg)"}`}
							>
								{status}
							</span>
						</div>
						<p className="mt-4 font-data text-2xl text-(--color-market-down-fg)">{loss}</p>
						<div className="mt-3 h-1.5 rounded bg-(--color-surface-panel-elevated)">
							<div className="h-full w-2/3 rounded bg-(--color-risk-high-fg)" />
						</div>
					</div>
				))}
			</div>
		</main>
	);
}

function RiskIncidentDashboard() {
	return (
		<main
			data-info-level="l1"
			data-info-unit="risk-dashboard"
			data-testid="risk-dashboard"
			className="h-full overflow-auto"
		>
			<h2 className="mb-3 text-sm font-medium">风险事件记录</h2>
			<div className="divide-y divide-(--color-border-subtle) rounded-(--radius-sm) border border-(--color-border-subtle)">
				{RISK_EVENTS.map(([time, title, detail, status]) => (
					<div key={`${time}-${title}`} className="grid grid-cols-[4rem_1fr_5rem] gap-3 p-3 text-xs">
						<span className="font-data text-(--color-foreground-tertiary)">{time}</span>
						<span>
							<strong className="font-medium text-(--color-foreground)">{title}</strong>
							<span className="ml-3 text-(--color-foreground-secondary)">{detail}</span>
						</span>
						<span className="text-right text-(--color-status-healthy-fg)">{status}</span>
					</div>
				))}
			</div>
		</main>
	);
}

function RiskActivityRail({
	onSelectBreach,
	onOpenStress,
}: {
	readonly onSelectBreach: (id: string) => void;
	readonly onOpenStress: () => void;
}) {
	const breaches = [
		["rb-001", "最大回撤", "当前 3.45% / 阈值 5.00%", "69%", "单日 VaR 超限"],
		["rb-002", "科技行业集中度", "当前 32.1% / 限制 40.00%", "80.2%", ""],
		["rb-003", "VaR(95%)", "当前 1.23% / 阈值 2.50%", "49.2%", ""],
	] as const;
	return (
		<aside
			data-info-level="l1"
			data-info-unit="risk-activity-rail"
			data-testid="risk-activity-rail"
			className="h-full border-l border-(--color-border-subtle) bg-(--color-surface-panel-base)"
			aria-label="风险活动面板"
		>
			<div className="flex h-[41px] items-center gap-0.5 border-b border-(--color-border-subtle) px-0 py-1">
				<span className="ml-3 rounded bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)] px-2 py-1 text-xs text-(--color-accent)">
					Breaches
				</span>
				<button type="button" className="px-2 py-1 text-xs text-(--color-foreground-tertiary)" onClick={onOpenStress}>
					压力测试
				</button>
			</div>
			<div className="mt-1 flex h-[34px] items-center gap-2 px-3 py-2">
				<h2 className="text-base font-medium">
					⌄ 活跃突破<span className="sr-only">风控告警</span>
				</h2>
				<span className="ml-auto text-xs leading-[inherit] text-(--color-foreground-tertiary)">0 突破</span>
			</div>
			<div className="flex h-[90px] flex-col items-center justify-center gap-2 px-3 py-4">
				<span className="text-(--color-status-healthy-fg)">✓</span>
				<p className="text-xs text-(--color-foreground-tertiary)">所有指标在安全范围内</p>
			</div>
			<div className="px-3">
				{breaches.map(([id, title, detail, value, legacyTitle]) => (
					<button
						key={id}
						type="button"
						aria-label={`${legacyTitle || title} ${detail}`}
						onClick={() => onSelectBreach(id)}
						className="flex h-[55px] w-full items-start gap-2 border-b border-(--color-border-subtle) py-1.5 text-left hover:bg-(--color-interaction-hover-subtle-bg)"
					>
						<span
							aria-hidden="true"
							className={`relative size-7 shrink-0 rounded-full ${id === "rb-003" ? "bg-[conic-gradient(var(--color-status-healthy-fg)_0_49%,var(--color-surface-panel-elevated)_49%_100%)]" : "bg-[conic-gradient(var(--color-risk-medium-fg)_0_72%,var(--color-surface-panel-elevated)_72%_100%)]"}`}
						>
							<i className="absolute inset-[3px] rounded-full bg-(--color-surface-panel-base)" />
						</span>
						<div className="min-w-0 flex-1">
							<div className="text-[12px] leading-[1.4] text-(--color-foreground-secondary)">
								{title}
								{legacyTitle && <span className="sr-only">{legacyTitle}</span>}
							</div>
							<div className="mt-px text-xs leading-[inherit] text-(--color-foreground-tertiary)">{detail}</div>
							<div className="mt-1 h-1 rounded bg-(--color-surface-panel-elevated)">
								<i
									className={`block h-full rounded ${id === "rb-003" ? "w-1/2 bg-(--color-status-healthy-fg)" : "w-3/4 bg-(--color-risk-medium-fg)"}`}
								/>
							</div>
						</div>
						<span
							className={`shrink-0 font-data text-xs font-semibold ${id === "rb-003" ? "text-(--color-status-healthy-fg)" : "text-(--color-risk-high-fg)"}`}
						>
							{value}
						</span>
					</button>
				))}
			</div>
		</aside>
	);
}

function RiskAnalysisBand({ onOpenRules }: { readonly onOpenRules: () => void }) {
	return (
		<section
			data-info-level="l2"
			data-info-unit="risk-analysis-band"
			data-testid="risk-analysis-band"
			className="flex h-full flex-col overflow-hidden border-t border-(--color-border-subtle) bg-(--color-surface-panel-elevated)"
		>
			<div className="flex h-[43px] shrink-0 items-center gap-3 border-b border-(--color-border-subtle) px-3 py-2">
				<h2 className="text-xs font-medium">风险总览</h2>
				<span className="text-xs leading-[inherit] text-(--color-foreground-tertiary)">
					资产风险热力矩阵 · 最近事件
				</span>
				<div className="ml-auto flex items-center gap-1 text-[12px] font-medium text-(--color-foreground-tertiary)">
					<span className="rounded bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)] px-2 py-1 text-(--color-accent)">
						全部
					</span>
					<span className="px-2 py-1">警告</span>
					<span className="px-2 py-1">突破</span>
					<span className="px-2 py-1">已处理</span>
					<Button type="button" size="xs" variant="ghost" aria-label="查看风险规则" onClick={onOpenRules}>
						查看全部 →
					</Button>
				</div>
			</div>
			<div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
				<div className="grid h-full grid-cols-[320px_1fr] gap-4">
					<div className="flex flex-col gap-2">
						<div className="flex items-center gap-1.5">
							<span className="text-[12px] font-medium">资产风险热力图</span>
							<span className="text-xs leading-[inherit] text-(--color-foreground-tertiary)">近 20 日 VaR 贡献</span>
						</div>
						<div className="flex items-center gap-2 text-xs leading-[inherit] text-(--color-foreground-tertiary)">
							<span>✓ 阈值内</span>
							<span>! 接近阈值</span>
							<span>VaR 2.50% / 回撤 5%</span>
						</div>
						<div className="grid h-[86px] w-[130px] grid-cols-6 gap-1 overflow-hidden rounded border border-(--color-accent) p-1">
							{RISK_HEATMAP_CELLS.map((cellId, index) => (
								<span
									key={cellId}
									className={`rounded-sm ${index % 6 === 0 ? "bg-[color-mix(in_oklch,var(--color-risk-critical-fg)_45%,transparent)]" : index % 4 === 0 ? "bg-[color-mix(in_oklch,var(--color-status-healthy-fg)_30%,transparent)]" : "bg-(--color-surface-panel-base)"}`}
								/>
							))}
						</div>
					</div>
					<div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-2">
						{RISK_EVENTS.map(([time, title, detail, status]) => (
							<article
								key={`${time}-${title}`}
								className="flex cursor-pointer items-start gap-2 border-b border-(--color-border-subtle) py-1.5"
							>
								<p className="flex min-w-[50px] shrink-0 items-center gap-1 font-data text-[12px] text-(--color-foreground-tertiary)">
									<i
										className={`size-1.5 rounded-full ${status === "监控中" ? "bg-(--color-risk-medium-fg)" : "bg-(--color-status-healthy-fg)"}`}
									/>
									{time}
								</p>
								<div className="min-w-0 flex-1">
									<h3 className="text-[12px] leading-[1.4] text-(--color-foreground-secondary)">{title}</h3>
									<p className="mt-px text-xs leading-[inherit] text-(--color-foreground-tertiary)">{detail}</p>
								</div>
								<span
									className={`shrink-0 rounded px-1.5 py-px text-xs leading-[inherit] font-medium ${status === "监控中" ? "bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)] text-(--color-accent)" : "bg-[color-mix(in_oklch,var(--color-status-healthy-fg)_10%,transparent)] text-(--color-status-healthy-fg)"}`}
								>
									{status}
								</span>
							</article>
						))}
					</div>
				</div>
			</div>
		</section>
	);
}

export function RiskStressDetailDrawer({ open, onClose }: { readonly open: boolean; readonly onClose: () => void }) {
	return (
		<Drawer open={open} onClose={onClose} title="压力测试证据">
			<div className="space-y-3 pb-6">
				<p>本面板只呈现后端已生成的场景损失，不会发起新的计算，也不改变订单或风险阈值。</p>
				<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
					<p className="text-xs text-(--color-foreground-tertiary)">PIT provenance</p>
					<p className="mt-2 font-data text-xs">
						decision 09:30 · knowledge 09:25 · publication 09:20 · snapshot ds-119
					</p>
				</div>
				<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
					<p className="text-xs text-(--color-foreground-tertiary)">可用性</p>
					<p className="mt-2">3 个场景可用，1 个场景因 source_snapshot_missing 明确不可用。</p>
				</div>
			</div>
		</Drawer>
	);
}

export function RiskRuleEditorSheet({ open, onClose }: { readonly open: boolean; readonly onClose: () => void }) {
	return (
		<Sheet
			open={open}
			onOpenChange={(next) => {
				if (!next) onClose();
			}}
		>
			<SheetContent side="right" aria-describedby="risk-rule-description" className="p-5">
				<SheetHeader>
					<SheetTitle>风险规则</SheetTitle>
					<SheetDescription id="risk-rule-description">只读规则预览</SheetDescription>
				</SheetHeader>
				<div className="mt-6 flex-1 space-y-4 text-sm">
					<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
						<p className="text-xs text-(--color-foreground-tertiary)">行业集中度阈值</p>
						<p className="mt-2 font-data text-lg">40%</p>
					</div>
					<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
						<p className="text-xs text-(--color-foreground-tertiary)">最大回撤阈值</p>
						<p className="mt-2 font-data text-lg">5.00%</p>
					</div>
					<p className="rounded-(--radius-sm) bg-(--color-surface-panel-elevated) p-3 text-(--color-foreground-secondary)">
						当前公开合同没有规则写入端点，因此不会伪造保存结果。
					</p>
				</div>
				<SheetFooter>
					<Button type="button" disabled>
						保持只读
					</Button>
				</SheetFooter>
			</SheetContent>
		</Sheet>
	);
}

export function RiskMockWorkspace() {
	const [tab, setTab] = useState<RiskTab>("overview");
	const [breachId, setBreachId] = useState<string | null>(null);
	const [stressOpen, setStressOpen] = useState(false);
	const [rulesOpen, setRulesOpen] = useState(false);

	return (
		<>
			<ShellHeaderExtension>
				<span className="-ml-2 whitespace-nowrap text-xs text-(--color-foreground-secondary)">Risk-On</span>
			</ShellHeaderExtension>
			<AnalyticalLayout
				className="pb-(--height-status-bar) [--height-analysis-band:195px] [--height-main-min:379px] [--height-strip-min:170px] [--width-activity:316px] max-[1280px]:[--height-analysis-band:257px] min-[1440px]:[--height-analysis-band:204px]"
				analysisSpansActivity
				strip={
					<div>
						<RiskPrimaryStrip />
						<RiskGaugeBand />
						<RiskTabBar tab={tab} onChange={setTab} />
					</div>
				}
				main={
					<div className="h-full min-h-0 p-4">
						{tab === "overview" ? (
							<RiskOverviewDashboard />
						) : tab === "stress" ? (
							<RiskStressDashboard onOpenEvidence={() => setStressOpen(true)} />
						) : (
							<RiskIncidentDashboard />
						)}
					</div>
				}
				activity={
					<div className="h-full min-h-0 py-4 pr-4">
						<RiskActivityRail onSelectBreach={setBreachId} onOpenStress={() => setStressOpen(true)} />
					</div>
				}
				analysis={<RiskAnalysisBand onOpenRules={() => setRulesOpen(true)} />}
			/>
			<StatusBar />
			<Drawer open={breachId !== null} onClose={() => setBreachId(null)} title="告警详情">
				<div data-info-level="l2" data-info-unit="breach-detail">
					{breachId && <BreachDetailContent breachId={breachId} />}
				</div>
			</Drawer>
			<RiskStressDetailDrawer open={stressOpen} onClose={() => setStressOpen(false)} />
			<RiskRuleEditorSheet open={rulesOpen} onClose={() => setRulesOpen(false)} />
		</>
	);
}
