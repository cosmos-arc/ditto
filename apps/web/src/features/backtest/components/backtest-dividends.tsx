import type { BacktestDividendStatement } from "../types";

const money = (value: number) => value.toLocaleString("zh-CN", { maximumFractionDigits: 6 });
const labels: Record<string, string> = {
	receivable: "除息应收",
	cash_payment: "分红到账",
	tax_reserved: "预留补税",
	tax_payment: "税款扣付",
};

export function BacktestDividends({ statement }: { readonly statement: BacktestDividendStatement | null | undefined }) {
	if (!statement)
		return <p className="mb-3 text-xs text-(--color-foreground-secondary)">本报告没有已保存的股票现金分红事件。</p>;
	return (
		<details className="mb-3 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-3 text-xs">
			<summary className="cursor-pointer rounded-(--radius-sm) font-medium focus-visible:outline-2 focus-visible:outline-offset-4">
				股票现金分红账本（{statement.events.length} 个事件）
			</summary>
			<p className="my-3">{statement.policy}</p>
			<p>金额单位：人民币元（CNY）；日期：交易所当地日期。净资产 = 现金 + 应收 + 持仓市值 − 待扣税款。</p>
			{statement.events.map((event) => (
				<details key={event.eventId} className="my-3">
					<summary className="cursor-pointer focus-visible:outline-2">
						{event.symbol} · 登记 {event.record} · {event.quantity} 股 · 税前每股 {money(event.grossPerShare)} 元
					</summary>
					<p>
						实施公告 {event.announcement}；除息 {event.ex}；派息 {event.pay}。
					</p>
					<p className="break-all">来源：{event.source}</p>
				</details>
			))}
			<ul aria-label="分红与税款流水" className="my-3">
				{statement.entries.map((entry) => (
					<li key={`${entry.eventId}-${entry.day}-${entry.kind}-${entry.acquired}`}>
						{entry.day} · {labels[entry.kind]} · {money(entry.amount)} 元
						{entry.quantity ? ` · ${entry.quantity} 股` : ""}
						{entry.acquired ? ` · 取得日 ${entry.acquired}` : ""}
					</li>
				))}
			</ul>
			{/* biome-ignore lint/a11y/noNoninteractiveTabindex: keyboard users scroll the daily accounting table. */}
			<section className="overflow-x-auto" aria-label="分红每日对账滚动区域" tabIndex={0}>
				<table aria-label="分红每日对账" className="w-full whitespace-nowrap text-left font-data">
					<thead>
						<tr>
							{["日期", "现金", "可用现金", "应收", "待扣税", "持仓市值", "净资产"].map((label) => (
								<th key={label} scope="col" className="p-2">
									{label}
								</th>
							))}
						</tr>
					</thead>
					<tbody>
						{statement.balances.map((row) => (
							<tr key={row.day}>
								<th scope="row" className="p-2">
									{row.day}
								</th>
								{[row.cash, row.available, row.receivable, row.tax, row.market, row.nav].map((value, index) => (
									<td key={["cash", "available", "receivable", "tax", "market", "nav"][index]} className="p-2">
										{money(value)}
									</td>
								))}
							</tr>
						))}
					</tbody>
				</table>
			</section>
		</details>
	);
}
