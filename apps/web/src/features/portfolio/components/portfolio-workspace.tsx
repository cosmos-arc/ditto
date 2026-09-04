import { useState } from "react";
import { Drawer } from "@/components/indicator/overlay/drawer";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { AnalyticalLayout, ShellHeaderExtension } from "@/features/shell";

type PortfolioTab = "positions" | "trades" | "attribution";

type PositionRow = {
	readonly name: string;
	readonly code: string;
	readonly quantity: string;
	readonly available: string;
	readonly cost: string;
	readonly last: string;
	readonly marketValue: string;
	readonly pnl: string;
	readonly pnlPercent: string;
	readonly dayPnl: string;
	readonly frozen?: boolean;
};

type TradeRow = {
	readonly time: string;
	readonly name: string;
	readonly code: string;
	readonly side: "买" | "卖";
	readonly quantity: string;
	readonly price: string;
	readonly amount: string;
	readonly source: string;
};

const POSITIONS: readonly PositionRow[] = [
	{
		name: "贵州茅台",
		code: "600519.SH",
		quantity: "200",
		available: "100",
		cost: "1,680.00",
		last: "1,756.80",
		marketValue: "351,360.00",
		pnl: "+15,360.00",
		pnlPercent: "+4.57%",
		dayPnl: "+2,400.00",
		frozen: true,
	},
	{
		name: "宁德时代",
		code: "300750.SZ",
		quantity: "500",
		available: "500",
		cost: "198.50",
		last: "210.30",
		marketValue: "105,150.00",
		pnl: "+5,900.00",
		pnlPercent: "+5.95%",
		dayPnl: "+1,500.00",
	},
	{
		name: "比亚迪",
		code: "002594.SZ",
		quantity: "300",
		available: "300",
		cost: "265.00",
		last: "258.40",
		marketValue: "77,520.00",
		pnl: "-1,980.00",
		pnlPercent: "-2.49%",
		dayPnl: "-780.00",
	},
	{
		name: "招商银行",
		code: "600036.SH",
		quantity: "1,000",
		available: "1,000",
		cost: "35.20",
		last: "36.85",
		marketValue: "36,850.00",
		pnl: "+1,650.00",
		pnlPercent: "+4.69%",
		dayPnl: "+450.00",
	},
	{
		name: "中国平安",
		code: "601318.SH",
		quantity: "800",
		available: "0",
		cost: "48.90",
		last: "50.12",
		marketValue: "40,096.00",
		pnl: "+976.00",
		pnlPercent: "+2.49%",
		dayPnl: "+320.00",
		frozen: true,
	},
	{
		name: "腾讯控股",
		code: "00700.HK",
		quantity: "200",
		available: "200",
		cost: "368.00",
		last: "385.40",
		marketValue: "77,080.00",
		pnl: "+3,480.00",
		pnlPercent: "+4.73%",
		dayPnl: "+1,200.00",
	},
	{
		name: "中芯国际",
		code: "688981.SH",
		quantity: "600",
		available: "600",
		cost: "82.50",
		last: "78.90",
		marketValue: "47,340.00",
		pnl: "-2,160.00",
		pnlPercent: "-4.36%",
		dayPnl: "-540.00",
	},
	{
		name: "药明康德",
		code: "603259.SH",
		quantity: "400",
		available: "400",
		cost: "65.00",
		last: "62.30",
		marketValue: "24,920.00",
		pnl: "-1,080.00",
		pnlPercent: "-4.15%",
		dayPnl: "-260.00",
	},
];

const TRADES: readonly TradeRow[] = [
	{
		time: "10:18:35",
		name: "贵州茅台",
		code: "600519.SH",
		side: "卖",
		quantity: "100",
		price: "1,756.80",
		amount: "175,680.00",
		source: "Alpha v3",
	},
	{
		time: "10:04:12",
		name: "宁德时代",
		code: "300750.SZ",
		side: "买",
		quantity: "200",
		price: "210.30",
		amount: "42,060.00",
		source: "均值回归 v2",
	},
	{
		time: "09:48:09",
		name: "招商银行",
		code: "600036.SH",
		side: "买",
		quantity: "500",
		price: "36.85",
		amount: "18,425.00",
		source: "风险再平衡",
	},
	{
		time: "09:36:44",
		name: "中芯国际",
		code: "688981.SH",
		side: "卖",
		quantity: "200",
		price: "78.90",
		amount: "15,780.00",
		source: "止损规则",
	},
];

const SUMMARY = [
	{
		label: "收益为正，但最大回撤由科技集中度贡献",
		value: "2,847,320.50",
		detail: "+12,450.80 (+0.44%)",
		tone: "neutral",
	},
	{ label: "总市值", value: "2,691,090.50", detail: "持仓市值", tone: "neutral" },
	{ label: "累计 PnL", value: "+191,090.50", detail: "+7.18% 收益率", tone: "up" },
	{ label: "查看回撤归因", value: "-3.24%", detail: "再平衡后科技权重 -2.4pp", tone: "healthy" },
] as const;

function toneClass(value: string): string {
	return value.startsWith("-") ? "text-(--color-market-down-fg)" : "text-(--color-market-up-fg)";
}

function PortfolioScopeStrip() {
	return (
		<div className="flex h-9 items-center gap-3 overflow-hidden border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-3 text-xs text-(--color-foreground-tertiary)">
			<span className="sr-only">组合总览</span>
			<span>
				账户: <span className="font-data text-(--color-foreground)">****8823</span>
			</span>
			<span aria-hidden="true" className="h-3 w-px bg-(--color-border-subtle)" />
			<span>
				市值: <span className="font-data text-(--color-foreground)">2,847,320.50</span>
			</span>
			<span aria-hidden="true" className="h-3 w-px bg-(--color-border-subtle)" />
			<span className="whitespace-nowrap text-(--color-market-up-fg)">
				<span aria-hidden="true" className="text-[.7em]">
					▲{" "}
				</span>
				当日 PnL: <span className="font-data">+12,450.80 (+0.44%)</span>
			</span>
			<span aria-hidden="true" className="h-3 w-px bg-(--color-border-subtle)" />
			<span>
				持仓: <span className="font-data text-(--color-foreground)">8 只</span>
			</span>
			<span aria-hidden="true" className="h-3 w-px bg-(--color-border-subtle)" />
			<span>
				可用: <span className="font-data text-(--color-foreground)">156,230.00</span>
			</span>
		</div>
	);
}

function PortfolioSummary() {
	return (
		<section aria-label="组合摘要" className="grid grid-cols-4 gap-2">
			{SUMMARY.map((item) => (
				<div
					key={item.label}
					className={`min-w-0 rounded-(--radius-sm) border px-3 py-2.5 ${item.tone === "healthy" ? "border-[color-mix(in_oklch,var(--color-status-healthy-fg)_45%,var(--color-border-subtle))]" : "border-(--color-border-subtle)"} bg-(--color-surface-panel-base)`}
				>
					{item === SUMMARY[0] && <span className="sr-only">总资产</span>}
					<p className="mb-1 text-[12px] leading-[1.35] text-(--color-foreground-tertiary)">{item.label}</p>
					<p
						className={`font-data text-[16px] leading-[1.35] font-semibold tabular-nums ${item.tone === "up" ? "text-(--color-market-up-fg)" : item.tone === "healthy" ? "text-(--color-market-down-fg)" : "text-(--color-foreground)"}`}
					>
						{item.tone === "up" && (
							<span aria-hidden="true" className="text-[.7em]">
								▲{" "}
							</span>
						)}
						{item.tone === "healthy" && (
							<span aria-hidden="true" className="text-[.7em]">
								▼{" "}
							</span>
						)}
						{item.value}
					</p>
					<p
						className={`mt-0.5 text-[12px] leading-[1.35] ${item.detail.startsWith("+") ? "text-(--color-market-up-fg)" : "text-(--color-foreground-tertiary)"}`}
					>
						{item.detail.startsWith("+") && (
							<span aria-hidden="true" className="text-[.7em]">
								▲{" "}
							</span>
						)}
						{item.detail}
					</p>
				</div>
			))}
		</section>
	);
}

function PortfolioTabs({
	tab,
	onTabChange,
}: {
	readonly tab: PortfolioTab;
	readonly onTabChange: (tab: PortfolioTab) => void;
}) {
	const tabs = [
		["positions", "持仓"],
		["trades", "交易"],
		["attribution", "归因"],
	] as const;

	return (
		<div
			className="flex items-center gap-0.5 border-b border-(--color-border-subtle) px-3 py-2"
			role="tablist"
			aria-label="Portfolio 分类"
		>
			{tabs.map(([id, label]) => (
				<button
					key={id}
					type="button"
					role="tab"
					aria-selected={tab === id}
					onClick={() => onTabChange(id)}
					className={`rounded-(--radius-sm) px-2 py-1 text-base leading-[19.5px] font-medium transition-colors ${tab === id ? "bg-[color-mix(in_oklch,var(--color-accent)_12%,transparent)] text-(--color-accent)" : "text-(--color-foreground-tertiary) hover:text-(--color-foreground)"}`}
				>
					{label}
				</button>
			))}
		</div>
	);
}

function PositionsTable({ onSelect }: { readonly onSelect: (position: PositionRow) => void }) {
	return (
		<div className="overflow-x-auto overflow-y-hidden rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-app)">
			<table className="w-full table-fixed border-collapse text-left text-[12px] leading-[18px]">
				<colgroup>
					<col className="w-[12%]" />
					<col className="w-[9%]" />
					<col className="w-[5%]" />
					<col className="w-[6.5%]" />
					<col className="w-[8.5%]" />
					<col className="w-[8.5%]" />
					<col className="w-[8.75%]" />
					<col className="w-[10.5%]" />
					<col className="w-[11.75%]" />
					<col className="w-[8.25%]" />
					<col className="w-[11.25%]" />
				</colgroup>
				<thead className="sticky top-0 z-10 bg-(--color-surface-app)">
					<tr className="border-b border-(--color-border-subtle) text-(--color-foreground-tertiary)">
						<th className="px-1.5 py-1 font-medium">标的</th>
						<th className="px-1.5 font-medium">代码</th>
						<th className="px-1.5 font-medium">方向</th>
						<th className="px-1.5 text-right font-medium">数量</th>
						<th className="px-1.5 text-right font-medium">可用</th>
						<th className="px-1.5 text-right font-medium">成本价</th>
						<th className="px-1.5 text-right font-medium">现价</th>
						<th className="px-1.5 text-right font-medium">市值</th>
						<th className="px-1.5 text-right font-medium">PNL</th>
						<th className="px-1.5 text-right font-medium">PNL%</th>
						<th className="px-1.5 text-right font-medium">当日盈亏</th>
					</tr>
				</thead>
				<tbody>
					{POSITIONS.map((position, index) => (
						<tr
							key={position.code}
							className={`${index === 0 ? "h-[37px]" : "h-[31px]"} border-b border-(--color-border-subtle) hover:bg-(--color-interaction-hover-subtle-bg)`}
						>
							<td className="p-0">
								<button
									type="button"
									aria-label={`查看 ${position.name} 持仓详情`}
									className="w-full px-1.5 py-1.5 text-left text-(--color-foreground)"
									onClick={() => onSelect(position)}
								>
									{position.name}
								</button>
							</td>
							<td className="px-1.5 font-data text-(--color-foreground)">{position.code}</td>
							<td className="px-1.5">多</td>
							<td className="px-1.5 text-right font-data">{position.quantity}</td>
							<td className="px-1.5 text-right font-data">
								{position.available}
								{position.frozen && (
									<span className="ml-1 rounded bg-(--color-surface-panel-elevated) px-1 text-xs leading-[inherit] text-(--color-foreground-tertiary)">
										T+1
									</span>
								)}
							</td>
							<td className="px-1.5 text-right font-data">{position.cost}</td>
							<td className="px-1.5 text-right font-data">{position.last}</td>
							<td className="px-1.5 text-right font-data">{position.marketValue}</td>
							<td className={`whitespace-nowrap px-1.5 text-right font-data ${toneClass(position.pnl)}`}>
								<span className="text-[.7em]">{position.pnl.startsWith("-") ? "▼ " : "▲ "}</span>
								{position.pnl}
							</td>
							<td className={`whitespace-nowrap px-1.5 text-right font-data ${toneClass(position.pnlPercent)}`}>
								<span className="text-[.7em]">{position.pnlPercent.startsWith("-") ? "▼ " : "▲ "}</span>
								{position.pnlPercent}
							</td>
							<td className={`whitespace-nowrap px-1.5 text-right font-data ${toneClass(position.dayPnl)}`}>
								<span className="text-[.7em]">{position.dayPnl.startsWith("-") ? "▼ " : "▲ "}</span>
								{position.dayPnl}
							</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}

function TradesTable({ onSelect }: { readonly onSelect: (trade: TradeRow) => void }) {
	return (
		<div className="h-full overflow-auto px-3 pt-3">
			<table className="w-full border-collapse text-left text-xs">
				<thead>
					<tr className="border-y border-(--color-border-subtle) text-(--color-foreground-tertiary)">
						<th className="px-2 py-2 font-normal">时间</th>
						<th className="px-2 font-normal">标的</th>
						<th className="px-2 font-normal">方向</th>
						<th className="px-2 text-right font-normal">数量</th>
						<th className="px-2 text-right font-normal">成交价</th>
						<th className="px-2 text-right font-normal">成交额</th>
						<th className="px-2 font-normal">来源</th>
					</tr>
				</thead>
				<tbody>
					{TRADES.map((trade) => (
						<tr
							key={`${trade.time}-${trade.code}`}
							className="border-b border-(--color-border-subtle) hover:bg-(--color-interaction-hover-subtle-bg)"
						>
							<td className="px-2 py-2 font-data">{trade.time}</td>
							<td className="p-0">
								<button
									type="button"
									aria-label={`查看 ${trade.name} 成交详情`}
									className="w-full px-2 py-2 text-left"
									onClick={() => onSelect(trade)}
								>
									{trade.name}
									<span className="ml-2 font-data text-(--color-foreground-tertiary)">{trade.code}</span>
								</button>
							</td>
							<td
								className={`px-2 ${trade.side === "买" ? "text-(--color-market-up-fg)" : "text-(--color-market-down-fg)"}`}
							>
								{trade.side}
							</td>
							<td className="px-2 text-right font-data">{trade.quantity}</td>
							<td className="px-2 text-right font-data">{trade.price}</td>
							<td className="px-2 text-right font-data">{trade.amount}</td>
							<td className="px-2 text-(--color-foreground-secondary)">{trade.source}</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}

function AttributionTable() {
	const rows = [
		["选股贡献", "+4.82%", "消费与科技"],
		["行业配置", "+1.74%", "低配金融"],
		["交易成本", "-0.31%", "滑点与费用"],
		["现金拖累", "-0.08%", "平均现金 5.4%"],
	] as const;
	return (
		<section className="p-4">
			<h2 className="mb-3 text-sm font-medium">收益归因</h2>
			<div className="grid grid-cols-2 gap-2">
				{rows.map(([label, value, detail]) => (
					<div
						key={label}
						className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-3"
					>
						<p className="text-xs text-(--color-foreground-tertiary)">{label}</p>
						<p className={`mt-1 font-data text-lg ${toneClass(value)}`}>{value}</p>
						<p className="mt-1 text-xs text-(--color-foreground-secondary)">{detail}</p>
					</div>
				))}
			</div>
		</section>
	);
}

function PortfolioPnlRail() {
	return (
		<aside
			className="flex h-full flex-col border-l border-(--color-border-subtle) bg-(--color-surface-panel-base)"
			aria-label="PnL 分析"
		>
			<header className="border-b border-(--color-border-subtle) px-3 py-2.5">
				<h2 className="text-base leading-[19.5px] font-semibold">PnL 曲线</h2>
				<p className="mt-0.5 text-[12px] leading-[18px] text-(--color-foreground-tertiary)">近 30 日 · 累计收益率</p>
				<select
					aria-label="选择对比基准"
					defaultValue="hs300"
					className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) px-1.5 py-0.5 text-[12px] leading-[18px] text-(--color-foreground-secondary)"
				>
					<option value="none">无基准</option>
					<option value="hs300">沪深 300</option>
					<option value="zz500">中证 500</option>
					<option value="cyb">创业板指</option>
				</select>
			</header>
			<div className="flex min-h-0 flex-1 flex-col gap-2 p-2">
				<div className="flex min-h-0 flex-1 flex-col gap-1.5 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-panel-elevated) p-2">
					<svg
						viewBox="0 0 260 300"
						className="min-h-[180px] w-full flex-1"
						role="img"
						aria-label="组合与沪深 300 累计收益曲线"
					>
						<defs>
							<linearGradient id="portfolio-pnl-fill" x1="0" y1="0" x2="0" y2="1">
								<stop offset="0" stopColor="var(--color-accent)" stopOpacity="0.22" />
								<stop offset="1" stopColor="var(--color-accent)" stopOpacity="0" />
							</linearGradient>
						</defs>
						{[44, 108, 172, 236].map((y) => (
							<line
								key={y}
								x1="0"
								y1={y}
								x2="260"
								y2={y}
								stroke="var(--color-border-subtle)"
								vectorEffect="non-scaling-stroke"
							/>
						))}
						<line
							x1="0"
							y1="208"
							x2="260"
							y2="208"
							stroke="var(--color-foreground-tertiary)"
							strokeDasharray="5 5"
							opacity="0.55"
							vectorEffect="non-scaling-stroke"
						/>
						<rect x="102" y="174" width="80" height="48" rx="2" fill="var(--color-market-down-fg)" opacity="0.07" />
						<path
							d="M0 226 C20 218 32 230 48 214 C70 190 84 198 102 174 C122 146 142 158 162 122 C184 94 204 118 222 78 C238 58 248 66 260 48 L260 300 L0 300 Z"
							fill="url(#portfolio-pnl-fill)"
						/>
						<path
							d="M0 226 C20 218 32 230 48 214 C70 190 84 198 102 174 C122 146 142 158 162 122 C184 94 204 118 222 78 C238 58 248 66 260 48"
							fill="none"
							stroke="var(--color-accent)"
							strokeWidth="2"
							vectorEffect="non-scaling-stroke"
						/>
						<polyline
							points="0,220 30,216 60,210 90,204 120,198 150,188 180,180 210,172 240,164 260,158"
							fill="none"
							stroke="var(--color-foreground-tertiary)"
							strokeDasharray="4 4"
							opacity="0.7"
							vectorEffect="non-scaling-stroke"
						/>
						<path
							d="M0 252 C24 248 42 258 58 242 C78 230 92 236 110 218 C134 205 152 212 170 192 C196 182 214 196 232 176 C246 166 254 170 260 164"
							fill="none"
							stroke="var(--color-market-down-fg)"
							strokeWidth="1.4"
							opacity="0.78"
							vectorEffect="non-scaling-stroke"
						/>
						<circle
							cx="260"
							cy="48"
							r="4"
							fill="var(--color-accent)"
							stroke="var(--color-surface-panel-elevated)"
							strokeWidth="2"
						/>
					</svg>
					<div className="flex gap-4 text-xs leading-[inherit] text-(--color-foreground-secondary)">
						<span>
							<i className="mr-1 inline-block h-px w-4 bg-(--color-accent)" />
							组合
						</span>
						<span>
							<i className="mr-1 inline-block h-px w-4 border-t border-dashed border-(--color-foreground-tertiary)" />
							沪深 300
						</span>
					</div>
					<div className="flex justify-between font-data text-xs leading-[inherit] text-(--color-foreground-tertiary)">
						<span>03-22</span>
						<span>04-05</span>
						<span>04-21</span>
					</div>
				</div>
				<div className="grid grid-cols-3 gap-1.5">
					{[
						["累计", "+7.18%"],
						["超额", "+1.42%"],
						["回撤", "-3.24%"],
					].map(([label, value]) => (
						<div key={label} className="rounded-(--radius-sm) border border-(--color-border-subtle) p-1.5">
							<p className="text-xs leading-[inherit] text-(--color-foreground-tertiary)">{label}</p>
							<p className={`mt-0.5 font-data text-[12px] font-semibold ${toneClass(value)}`}>
								<span aria-hidden="true" className="text-[.7em]">
									{value.startsWith("-") ? "▼ " : "▲ "}
								</span>
								{value}
							</p>
						</div>
					))}
				</div>
				<div className="flex min-h-[74px] items-center gap-2 py-1">
					<div className="relative size-16 shrink-0 rounded-full bg-[conic-gradient(var(--color-accent)_0_35%,var(--color-market-up-fg)_35%_60%,var(--color-market-down-fg)_60%_80%,var(--color-foreground-tertiary)_80%_100%)]">
						<span className="absolute inset-[14px] flex items-center justify-center rounded-full bg-(--color-surface-panel-base) font-data text-xs leading-[inherit]">
							4
						</span>
					</div>
					<div className="grid gap-0.5 text-xs leading-[inherit] text-(--color-foreground-tertiary)">
						<span>
							<i className="mr-1 inline-block size-1.5 rounded-sm bg-(--color-accent)" />
							消费 35%
						</span>
						<span>
							<i className="mr-1 inline-block size-1.5 rounded-sm bg-(--color-market-up-fg)" />
							新能源 25%
						</span>
						<span>
							<i className="mr-1 inline-block size-1.5 rounded-sm bg-(--color-market-down-fg)" />
							医药 20%
						</span>
						<span>
							<i className="mr-1 inline-block size-1.5 rounded-sm bg-(--color-foreground-tertiary)" />
							金融/科技 20%
						</span>
					</div>
				</div>
			</div>
		</aside>
	);
}

function PortfolioAnalysisBand() {
	const sectors = [
		["消费", "28% · +0.12"],
		["新能源", "20% · +0.09"],
		["科技", "16% · +0.05"],
		["金融", "14% · +0.06"],
		["医药", "10% · -0.04"],
	] as const;
	return (
		<section
			className="h-full border-t border-(--color-border-subtle) bg-(--color-surface-panel-elevated)"
			aria-label="Portfolio 风险指标"
		>
			<div className="flex h-[43px] items-center px-3">
				<h2 className="rounded bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)] px-2 py-1 text-[12px] text-(--color-accent)">
					风险指标
				</h2>
			</div>
			<div className="grid h-[calc(100%-43px)] grid-cols-[1.05fr_1.25fr_.9fr] gap-2.5 px-3 py-2.5">
				<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2">
					<div className="mb-2 flex items-center justify-between">
						<h3 className="text-[12px] font-semibold text-(--color-foreground-secondary)">组合风险</h3>
						<span className="text-xs leading-[inherit] text-(--color-foreground-tertiary)">实时快照</span>
					</div>
					<div className="grid grid-cols-3 gap-2">
						{[
							["日波动率", "1.24%"],
							["Beta", "0.87"],
							["VaR 95%", "-38,240"],
						].map(([label, value]) => (
							<div key={label} className="rounded bg-(--color-surface-panel-base) p-2">
								<p className="text-xs leading-[inherit] text-(--color-foreground-tertiary)">{label}</p>
								<p
									className={`mt-0.5 font-data text-base font-semibold ${value.startsWith("-") ? "text-(--color-market-down-fg)" : ""}`}
								>
									{value}
								</p>
							</div>
						))}
					</div>
				</div>
				<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2">
					<div className="mb-2 flex items-center justify-between">
						<h3 className="text-[12px] font-semibold text-(--color-foreground-secondary)">集中度热区</h3>
						<span className="text-xs leading-[inherit] text-(--color-foreground-tertiary)">行业权重 / 今日贡献</span>
					</div>
					<div className="grid grid-cols-5 gap-1">
						{sectors.map(([label, value], index) => (
							<div
								key={label}
								className={`flex h-14 flex-col justify-between rounded border p-2 ${index < 2 ? "border-[color-mix(in_oklch,var(--color-accent)_32%,var(--color-border-subtle))] bg-[color-mix(in_oklch,var(--color-accent)_10%,var(--color-surface-panel-base))]" : "border-(--color-border-subtle) bg-(--color-surface-panel-base)"}`}
							>
								<span className="text-xs leading-[inherit] text-(--color-foreground-tertiary)">{label}</span>
								<span className="font-data text-[11px]">{value}</span>
							</div>
						))}
					</div>
				</div>
				<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2">
					<div className="mb-2 flex items-center justify-between">
						<h3 className="text-[12px] font-semibold text-(--color-foreground-secondary)">交易约束</h3>
						<span className="text-xs leading-[inherit] text-(--color-foreground-tertiary)">A 股规则</span>
					</div>
					<ul className="space-y-2 text-[12px] text-(--color-foreground-secondary)">
						<li>
							● T+1 冻结 <span className="float-right font-data">900 股</span>
						</li>
						<li>
							● 可卖市值 <span className="float-right font-data">2.34M</span>
						</li>
						<li>
							● 风险中心联动 <span className="float-right text-(--color-status-healthy-fg)">正常</span>
						</li>
					</ul>
				</div>
			</div>
		</section>
	);
}

export function PortfolioPositionDetailDrawer({
	position,
	onClose,
}: {
	readonly position: PositionRow | null;
	readonly onClose: () => void;
}) {
	return (
		<Drawer open={position !== null} onClose={onClose} title="持仓详情">
			<div className="space-y-4 pb-6">
				{position && (
					<>
						<div>
							<p className="text-lg font-semibold text-(--color-foreground)">{position.name}</p>
							<p className="mt-1 font-data">{position.code}</p>
						</div>
						<dl className="grid grid-cols-2 gap-3">
							{[
								["数量", position.quantity],
								["可用", position.available],
								["成本价", position.cost],
								["现价", position.last],
								["市值", position.marketValue],
								["累计 PnL", position.pnl],
							].map(([label, value]) => (
								<div key={label} className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
									<dt className="text-xs text-(--color-foreground-tertiary)">{label}</dt>
									<dd className="mt-1 font-data text-(--color-foreground)">{value}</dd>
								</div>
							))}
						</dl>
						<p className="rounded-(--radius-sm) bg-(--color-surface-panel-elevated) p-3 text-xs">
							持仓详情为只读视图；交易动作请前往 Signals / Orders 复核。
						</p>
					</>
				)}
			</div>
		</Drawer>
	);
}

export function PortfolioTradeDetailDialog({
	trade,
	onClose,
}: {
	readonly trade: TradeRow | null;
	readonly onClose: () => void;
}) {
	return (
		<Dialog
			open={trade !== null}
			onOpenChange={(open) => {
				if (!open) onClose();
			}}
		>
			<DialogContent aria-describedby="portfolio-trade-description">
				<DialogHeader>
					<DialogTitle>成交详情</DialogTitle>
					<DialogDescription id="portfolio-trade-description">只读成交证据，不修改订单或组合状态。</DialogDescription>
				</DialogHeader>
				{trade && (
					<div className="grid grid-cols-2 gap-3 text-sm">
						<p>
							标的：<span className="font-medium">{trade.name}</span>
						</p>
						<p>
							代码：<span className="font-data">{trade.code}</span>
						</p>
						<p>
							成交时间：<span className="font-data">{trade.time}</span>
						</p>
						<p>
							方向：<span>{trade.side}</span>
						</p>
						<p>
							成交额：<span className="font-data">{trade.amount}</span>
						</p>
						<p>来源：{trade.source}</p>
					</div>
				)}
				<DialogFooter>
					<Button type="button" variant="outline" onClick={onClose}>
						关闭
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}

export function PortfolioMockWorkspace() {
	const [tab, setTab] = useState<PortfolioTab>("positions");
	const [position, setPosition] = useState<PositionRow | null>(null);
	const [trade, setTrade] = useState<TradeRow | null>(null);

	return (
		<>
			<ShellHeaderExtension>
				<span className="whitespace-nowrap text-xs tracking-[.01em] text-(--color-foreground-tertiary)">
					交易 · 组合
				</span>
			</ShellHeaderExtension>
			<AnalyticalLayout
				className="[--height-analysis-band:220px] [--width-activity:clamp(16.25rem,20vw,17.75rem)]"
				strip={<PortfolioScopeStrip />}
				main={
					<main className="flex h-full min-h-0 flex-col gap-6 overflow-hidden p-3">
						<PortfolioSummary />
						<PortfolioTabs tab={tab} onTabChange={setTab} />
						<div className="min-h-0">
							{tab === "positions" ? (
								<PositionsTable onSelect={setPosition} />
							) : tab === "trades" ? (
								<TradesTable onSelect={setTrade} />
							) : (
								<AttributionTable />
							)}
						</div>
					</main>
				}
				activity={<PortfolioPnlRail />}
				analysis={<PortfolioAnalysisBand />}
			/>
			<PortfolioPositionDetailDrawer position={position} onClose={() => setPosition(null)} />
			<PortfolioTradeDetailDialog trade={trade} onClose={() => setTrade(null)} />
		</>
	);
}
