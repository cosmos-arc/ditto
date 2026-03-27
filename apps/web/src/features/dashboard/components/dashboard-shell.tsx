import { AppShell } from "@/components/layouts/app-shell";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function DashboardShell() {
	return (
		<AppShell activeNavKey="dashboard">
			<div className="p-6">
				<div className="grid grid-cols-3 gap-4">
					{/* Card 1: 六域 Token 展示 */}
					<Card>
						<CardHeader>
							<CardTitle>六域 Token</CardTitle>
							<CardDescription>
								Market / Risk / Execution / System / Data / Model
							</CardDescription>
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
									<span className="inline-block size-3 rounded-sm bg-risk-normal" />
									<span className="text-risk-normal">正常</span>
									<span className="inline-block size-3 rounded-sm bg-risk-watch ml-2" />
									<span className="text-risk-watch">关注</span>
									<span className="inline-block size-3 rounded-sm bg-risk-elevated ml-2" />
									<span className="text-risk-elevated">预警</span>
									<span className="inline-block size-3 rounded-sm bg-risk-breach ml-2" />
									<span className="text-risk-breach">突破</span>
								</div>
								<div className="flex items-center gap-2">
									<span className="inline-block size-3 rounded-sm bg-execution-filled" />
									<span className="text-execution-filled">Filled</span>
									<span className="inline-block size-3 rounded-sm bg-execution-pending ml-2" />
									<span className="text-execution-pending">Pending</span>
									<span className="inline-block size-3 rounded-sm bg-execution-rejected ml-2" />
									<span className="text-execution-rejected">Rejected</span>
								</div>
								<div className="flex items-center gap-2">
									<span className="inline-block size-3 rounded-sm bg-system-online" />
									<span className="text-system-online">Online</span>
									<span className="inline-block size-3 rounded-sm bg-system-degraded ml-2" />
									<span className="text-system-degraded">Degraded</span>
									<span className="inline-block size-3 rounded-sm bg-system-offline ml-2" />
									<span className="text-system-offline">Offline</span>
								</div>
								<div className="flex items-center gap-2">
									<span className="inline-block size-3 rounded-sm bg-data-fresh" />
									<span className="text-data-fresh">Fresh</span>
									<span className="inline-block size-3 rounded-sm bg-data-stale ml-2" />
									<span className="text-data-stale">Stale</span>
									<span className="inline-block size-3 rounded-sm bg-data-missing ml-2" />
									<span className="text-data-missing">Missing</span>
								</div>
								<div className="flex items-center gap-2">
									<span className="inline-block size-3 rounded-sm bg-model-accepted" />
									<span className="text-model-accepted">Accepted</span>
									<span className="inline-block size-3 rounded-sm bg-model-validating ml-2" />
									<span className="text-model-validating">Validating</span>
									<span className="inline-block size-3 rounded-sm bg-model-failed ml-2" />
									<span className="text-model-failed">Failed</span>
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
								compact (30px) / comfortable (36px) / ultra-compact (26px)
							</CardDescription>
						</CardHeader>
						<CardContent>
							<div
								className="space-y-1 text-sm font-mono"
								style={{
									fontSize: "var(--grid-font-size, 12px)",
									lineHeight: "var(--grid-row-height, 30px)",
								}}
							>
								{["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"].map((ticker) => (
									<div
										key={ticker}
										className="flex items-center rounded border border-border px-2"
										style={{
											height: "var(--grid-row-height, 30px)",
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
							<CardDescription>app → chrome → canvas → panel → elevated → raised → active</CardDescription>
						</CardHeader>
						<CardContent>
							<div className="space-y-1 rounded-md p-3 text-sm">
								<div className="rounded bg-surface-app p-2">surface-app</div>
								<div className="rounded bg-surface-chrome p-2">surface-chrome</div>
								<div className="rounded bg-surface-canvas p-2">surface-canvas</div>
								<div className="rounded bg-surface-panel p-2">surface-panel</div>
								<div className="rounded bg-surface-elevated p-2">surface-elevated</div>
								<div className="rounded bg-surface-raised p-2">surface-raised</div>
								<div className="rounded bg-surface-active p-2">surface-active</div>
							</div>
						</CardContent>
					</Card>
				</div>
			</div>
		</AppShell>
	);
}
