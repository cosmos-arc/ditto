import { useTheme } from "@/hooks/use-theme";
import { useDensity } from "@/hooks/use-density";
import { Button } from "@/components/ui/button";
import type { ReactNode } from "react";

const NAV_ITEMS = [
	{ label: "Dashboard", key: "dashboard", icon: "home" },
	{ label: "行情数据", key: "market", icon: "query_stats" },
	{ label: "因子研究", key: "research", icon: "science" },
	{ label: "组合管理", key: "portfolio", icon: "pie_chart" },
	{ label: "策略中心", key: "strategy", icon: "psychology" },
	{ label: "风控中心", key: "risk", icon: "settings_input_component" },
] as const;

const FOOTER_ITEMS = [
	{ label: "帮助", key: "help", icon: "help" },
	{ label: "设置", key: "settings", icon: "settings" },
] as const;

interface AppShellProps {
	readonly activeNavKey?: string;
	readonly children: ReactNode;
}

export function AppShell({ activeNavKey, children }: AppShellProps) {
	const { theme, toggleTheme } = useTheme();
	const { density, cycleDensity } = useDensity();

	return (
		<div className="flex h-screen bg-surface-app text-text-primary">
			{/* 侧边栏 */}
			<nav
				aria-label="主导航"
				className="flex w-48 shrink-0 flex-col"
			>
				{/* 品牌标识 */}
				<div className="border-b border-outline/20 px-4 py-4">
					<div className="text-lg font-black tracking-tight">Ditto Terminal</div>
					<div className="text-[10px] uppercase tracking-widest text-blue-500 opacity-80">
						Institutional Grade
					</div>
				</div>

				{/* 主导航 */}
				<ul className="flex-1 space-y-1 px-2">
					{NAV_ITEMS.map((item) => {
						const isActive = item.key === activeNavKey;
						return (
							<li key={item.key}>
								<button
									type="button"
									className={`flex w-full items-center gap-3 px-2 py-1 text-[13px] font-medium transition-all duration-(--duration-fast) ${
										isActive
											? "border-r-2 border-blue-500 bg-state-selected-soft-bg text-text-primary"
											: "text-text-tertiary hover:bg-surface-raised hover:text-text-primary"
									}`}
								>
									<span
										className={`material-symbols-outlined ${isActive ? "filled" : ""}`}
									>
										{item.icon}
									</span>
									{item.label}
								</button>
							</li>
						);
					})}
				</ul>

				{/* 底部链接 */}
				<div className="space-y-1 border-t border-outline-subtle px-2 pt-2">
					{FOOTER_ITEMS.map((item) => (
						<li key={item.key}>
							<button
								type="button"
								className="flex w-full items-center gap-3 px-2 py-1 text-[13px] text-text-tertiary transition-all duration-(--duration-fast) hover:bg-surface-raised hover:text-text-primary"
							>
								<span className="material-symbols-outlined">{item.icon}</span>
								{item.label}
							</button>
						</li>
					))}
				</div>
			</nav>

			{/* 主区域 */}
			<div className="flex flex-1 flex-col overflow-hidden">
				{/* 顶栏 */}
				<header className="flex h-12 items-center justify-between border-b border-outline-subtle bg-surface-chrome px-4 font-medium text-[13px] tracking-tight leading-tight">
					<div className="flex items-center gap-8">
						<span className="text-xl font-bold tracking-tighter text-text-primary">Ditto</span>
						<div className="flex items-center gap-6">
							{(["Dev", "Staging", "Prod"] as const).map((env) => (
								<button
									key={env}
									type="button"
									className="px-2 py-1 text-text-tertiary transition-colors hover:bg-surface-raised hover:text-text-primary"
								>
									{env}
								</button>
							))}
						</div>
					</div>
					<div className="flex items-center gap-4">
						<button
							type="button"
							className="text-text-tertiary transition-colors hover:text-text-primary"
							aria-label="schedule"
						>
							<span className="material-symbols-outlined">schedule</span>
						</button>
						<button
							type="button"
							className="relative text-text-tertiary transition-colors hover:text-text-primary"
							aria-label="notifications"
						>
							<span className="material-symbols-outlined">notifications</span>
							<span className="absolute right-0 top-0 size-1.5 rounded-full bg-red-500" />
						</button>
						<button
							type="button"
							className="text-text-tertiary transition-colors hover:text-text-primary"
							aria-label="account"
						>
							<span className="material-symbols-outlined">account_circle</span>
						</button>
						<div className="mx-2 h-4 w-px bg-outline-subtle" />
						<Button variant="ghost" size="sm" onClick={toggleTheme}>
							{theme === "dark" ? "Light" : "Dark"}
						</Button>
						<Button variant="ghost" size="sm" onClick={cycleDensity}>
							{density}
						</Button>
					</div>
				</header>

				{/* 内容区 */}
				<main className="flex-1 overflow-auto">{children}</main>
			</div>
		</div>
	);
}
