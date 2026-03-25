import { useTheme } from "@/hooks/use-theme";
import { useDensity } from "@/hooks/use-density";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardFooter,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const NAV_ITEMS = [
	{ label: "Dashboard", key: "dashboard" },
	{ label: "行情数据", key: "market" },
	{ label: "因子研究", key: "factor" },
	{ label: "策略中心", key: "strategy" },
	{ label: "回测中心", key: "backtest" },
	{ label: "风控中心", key: "risk" },
] as const;

export function DashboardShell() {
	const { theme, toggleTheme } = useTheme();
	const { density, cycleDensity } = useDensity();

	return (
		<div className="flex h-screen bg-surface-app text-text-primary">
			{/* 侧边栏 */}
			<nav
				aria-label="主导航"
				className="flex w-56 shrink-0 flex-col border-r border-border bg-surface-panel"
			>
				<div className="flex h-14 items-center px-4">
					<span className="text-lg font-bold tracking-tight">Ditto</span>
				</div>
				<ul className="flex-1 space-y-1 px-2 py-2">
					{NAV_ITEMS.map((item) => (
						<li key={item.key}>
							<button
								type="button"
								className="flex w-full items-center rounded-md px-3 py-2 text-sm font-medium text-text-secondary transition-colors duration-(--duration-fast) hover:bg-surface-hover hover:text-text-primary"
							>
								{item.label}
							</button>
						</li>
					))}
				</ul>
			</nav>

			{/* 主区域 */}
			<div className="flex flex-1 flex-col overflow-hidden">
				{/* 顶栏 */}
				<header className="flex h-14 items-center justify-between border-b border-border bg-surface-panel px-4">
					<span className="text-sm font-semibold text-text-secondary">
						Dashboard
					</span>
					<div className="flex items-center gap-2">
						<Button variant="ghost" size="sm" onClick={toggleTheme}>
							{theme === "dark" ? "Light" : "Dark"}
						</Button>
						<Button variant="ghost" size="sm" onClick={cycleDensity}>
							{density}
						</Button>
					</div>
				</header>

				{/* 内容区 — 验证展示 */}
				<main className="flex-1 overflow-auto p-6">
					<div className="grid grid-cols-3 gap-4">
						{/* Card 1: 四色域展示 */}
						<Card>
							<CardHeader>
								<CardTitle>四色域 Token</CardTitle>
								<CardDescription>Market / Risk / Status / Signal</CardDescription>
							</CardHeader>
							<CardContent>
								<div className="space-y-2 text-sm">
									<div className="flex items-center gap-2">
										<span className="inline-block size-3 rounded-sm bg-market-up" />
										<span className="text-market-up">涨 Up</span>
										<span className="inline-block size-3 rounded-sm bg-market-down ml-2" />
										<span className="text-market-down">跌 Down</span>
										<span className="inline-block size-3 rounded-sm bg-market-flat ml-2" />
										<span className="text-market-flat">平 Flat</span>
									</div>
									<div className="flex items-center gap-2">
										<span className="inline-block size-3 rounded-sm bg-risk-low" />
										<span className="text-risk-low">低</span>
										<span className="inline-block size-3 rounded-sm bg-risk-medium ml-2" />
										<span className="text-risk-medium">中</span>
										<span className="inline-block size-3 rounded-sm bg-risk-high ml-2" />
										<span className="text-risk-high">高</span>
										<span className="inline-block size-3 rounded-sm bg-risk-critical ml-2" />
										<span className="text-risk-critical">危</span>
									</div>
									<div className="flex items-center gap-2">
										<span className="inline-block size-3 rounded-sm bg-status-success" />
										<span className="text-status-success">Success</span>
										<span className="inline-block size-3 rounded-sm bg-status-warning ml-2" />
										<span className="text-status-warning">Warning</span>
										<span className="inline-block size-3 rounded-sm bg-status-error ml-2" />
										<span className="text-status-error">Error</span>
									</div>
									<div className="flex items-center gap-2">
										<span className="inline-block size-3 rounded-sm bg-signal-buy" />
										<span className="text-signal-buy">Buy</span>
										<span className="inline-block size-3 rounded-sm bg-signal-sell ml-2" />
										<span className="text-signal-sell">Sell</span>
										<span className="inline-block size-3 rounded-sm bg-signal-hold ml-2" />
										<span className="text-signal-hold">Hold</span>
									</div>
								</div>
							</CardContent>
						</Card>

						{/* Card 2: shadcn 组件验证 */}
						<Card>
							<CardHeader>
								<CardTitle>shadcn/ui 组件</CardTitle>
								<CardDescription>Button / Card / Input 使用 Ditto Token</CardDescription>
							</CardHeader>
							<CardContent>
								<div className="space-y-3">
									<div className="flex gap-2">
										<Button size="sm">Default</Button>
										<Button size="sm" variant="outline">Outline</Button>
										<Button size="sm" variant="secondary">Secondary</Button>
										<Button size="sm" variant="destructive">Destructive</Button>
									</div>
									<Input placeholder="输入框示例..." />
								</div>
							</CardContent>
						</Card>

						{/* Card 3: 密度展示 */}
						<Card>
							<CardHeader>
								<CardTitle>当前密度</CardTitle>
								<CardDescription>
									{density === "compact" && "Compact (32px)"}
									{density === "comfortable" && "Comfortable (40px)"}
									{density === "ultra-compact" && "Ultra Compact (26px)"}
								</CardDescription>
							</CardHeader>
							<CardContent>
								<div
									className="space-y-1 text-sm font-mono"
									style={{
										fontSize: "var(--grid-font-size, 13px)",
										lineHeight: "var(--grid-row-height, 32px)",
									}}
								>
									{["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"].map((ticker) => (
										<div
											key={ticker}
											className="flex items-center rounded border border-border px-2"
											style={{
												height: "var(--grid-row-height, 32px)",
												paddingBlock: "var(--grid-cell-padding-y, 4px)",
											}}
										>
											<span className="flex-1">{ticker}</span>
											<span className="text-text-muted">
												{(Math.random() * 500 + 100).toFixed(2)}
											</span>
										</div>
									))}
								</div>
							</CardContent>
						</Card>

						{/* Card 4: Surface 层级 */}
						<Card>
							<CardHeader>
								<CardTitle>Surface 层级</CardTitle>
								<CardDescription>app → panel → elevated → hover → selected</CardDescription>
							</CardHeader>
							<CardContent>
								<div className="space-y-1 rounded-md p-3 text-sm">
									<div className="rounded bg-surface-app p-2">surface-app</div>
									<div className="rounded bg-surface-panel p-2">surface-panel</div>
									<div className="rounded bg-surface-elevated p-2">surface-elevated</div>
									<div className="rounded bg-surface-hover p-2">surface-hover</div>
									<div className="rounded bg-surface-selected p-2">surface-selected</div>
								</div>
							</CardContent>
						</Card>
					</div>
				</main>
			</div>
		</div>
	);
}
