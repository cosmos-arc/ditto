import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useFillLedger, useOrdersSummary } from "../hooks";

type OrderSide = "buy" | "sell";

interface MockOrder {
	readonly code: string;
	readonly name: string;
	readonly side: OrderSide;
	readonly qty: number;
	readonly price: number;
	readonly time: string;
}

type OrderTab = "pending" | "filled" | "cancelled";

const ORDERS: Record<OrderTab, readonly MockOrder[]> = {
	pending: [
		{ code: "600519.SH", name: "贵州茅台", side: "buy", qty: 100, price: 1750.0, time: "09:45" },
		{ code: "000858.SZ", name: "五粮液", side: "sell", qty: 500, price: 146.0, time: "10:15" },
	],
	filled: [
		{ code: "300750.SZ", name: "宁德时代", side: "buy", qty: 200, price: 210.5, time: "09:30" },
		{ code: "000001.SZ", name: "平安银行", side: "sell", qty: 5000, price: 12.1, time: "09:35" },
	],
	cancelled: [{ code: "601318.SH", name: "中国平安", side: "buy", qty: 1000, price: 45.0, time: "09:20" }],
};

const TAB_LABELS: Record<OrderTab, string> = {
	pending: "待成交",
	filled: "已成交",
	cancelled: "已撤单",
};

const DIRECTION_VARIANT = {
	BUY: "trade",
	SELL: "risk",
} as const;

function MockOrdersPanel() {
	const [activeTab, setActiveTab] = useState<OrderTab>("pending");
	const orders = ORDERS[activeTab];

	return (
		<ContextSection title="委托订单" count={orders.length}>
			<div className="flex gap-1 py-2">
				{(Object.keys(TAB_LABELS) as OrderTab[]).map((tab) => (
					<button
						key={tab}
						type="button"
						className={`rounded-(--radius-sm) px-2.5 py-1 text-xs font-medium transition-colors ${
							activeTab === tab
								? "bg-(--color-surface-2) text-(--color-foreground)"
								: "text-(--color-foreground-tertiary) hover:text-(--color-foreground-secondary)"
						}`}
						onClick={() => setActiveTab(tab)}
					>
						{TAB_LABELS[tab]}
					</button>
				))}
			</div>
			<div className="flex flex-col gap-0.5">
				{orders.map((order) => (
					<div
						key={`${order.code}-${order.time}`}
						className="flex items-center gap-2 rounded-(--radius-sm) px-2 py-1.5 hover:bg-(--color-interaction-hover-subtle-bg)"
					>
						<span
							className={`shrink-0 rounded-(--radius-sm) px-1 py-px text-xs font-semibold ${
								order.side === "buy"
									? "bg-(--color-market-up-bg) text-(--color-market-up-fg)"
									: "bg-(--color-market-down-bg) text-(--color-market-down-fg)"
							}`}
						>
							{order.side === "buy" ? "买" : "卖"}
						</span>
						<span className="flex-1 truncate text-xs font-medium text-(--color-foreground)">{order.name}</span>
						<span className="font-data text-xs tabular-nums text-(--color-foreground-tertiary)">{order.qty}股</span>
						<span className="font-data text-xs tabular-nums text-(--color-foreground-secondary)">
							@{order.price.toFixed(2)}
						</span>
						<span className="font-data text-xs tabular-nums text-(--color-foreground-muted)">{order.time}</span>
					</div>
				))}
			</div>
		</ContextSection>
	);
}

function LiveOrdersPanel() {
	const ordersQuery = useOrdersSummary();
	const ledgerQuery = useFillLedger();
	const orders = ordersQuery.data;
	const ledger = ledgerQuery.data;
	const fills = ledger?.fills ?? [];
	const total = orders
		? orders.pending + orders.submitted + orders.partial + orders.filled + orders.failed
		: fills.length;
	const isError = ordersQuery.isError || ledgerQuery.isError;
	const isLoading = !isError && (ordersQuery.isLoading || ledgerQuery.isLoading);

	function retryLiveOrders() {
		void Promise.all([ordersQuery.refetch(), ledgerQuery.refetch()]);
	}

	return (
		<ContextSection title="委托订单" count={total}>
			{isLoading && (
				<div role="status" aria-label="委托订单加载中" className="py-2">
					<LoadingSkeleton variant="panel" rows={3} />
				</div>
			)}
			{isError && (
				<div
					role="alert"
					className="my-2 flex flex-col items-start gap-2 rounded-(--radius-sm) border border-(--color-risk-critical-fg) px-3 py-3 text-sm text-(--color-foreground-secondary) sm:flex-row sm:items-center sm:justify-between"
				>
					<span>委托订单加载失败</span>
					<Button variant="outline" size="sm" onClick={retryLiveOrders}>
						重试
					</Button>
				</div>
			)}
			{!isLoading && !isError && (
				<>
					{fills.length > 0 && (
						<span role="status" aria-label="委托订单加载完成" className="sr-only">
							委托订单已加载，成交 {fills.length} 笔
						</span>
					)}
					<div className="flex items-center justify-between py-2">
						<span className="text-xs text-(--color-foreground-tertiary)">manual / paper</span>
						<span className="font-data text-xs text-(--color-foreground-tertiary)">成交 {fills.length}</span>
					</div>
					{fills.length === 0 ? (
						<div
							role="status"
							aria-label="委托订单状态"
							className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-3 py-4 text-sm text-(--color-foreground-secondary)"
						>
							尚未录入手工成交
						</div>
					) : (
						<div className="flex flex-col gap-0.5">
							{fills.map((fill) => (
								<div
									key={fill.id}
									className="flex items-center gap-2 rounded-(--radius-sm) px-2 py-1.5 hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<StatusBadge variant={DIRECTION_VARIANT[fill.direction]} label={fill.direction} size="sm" />
									<span className="min-w-0 flex-1 truncate font-data text-xs text-(--color-foreground)">{fill.id}</span>
									<span className="font-data text-xs tabular-nums text-(--color-foreground-tertiary)">
										{fill.quantity.toLocaleString()}
									</span>
									<span className="font-data text-xs tabular-nums text-(--color-foreground-secondary)">
										@{fill.fillPrice.toFixed(2)}
									</span>
								</div>
							))}
						</div>
					)}
				</>
			)}
		</ContextSection>
	);
}

export function PortfolioOverviewOrdersPanel() {
	return (
		<div data-info-level="l1" data-info-unit="orders-panel">
			{shouldUsePrototypeMocks() ? <MockOrdersPanel /> : <LiveOrdersPanel />}
		</div>
	);
}
