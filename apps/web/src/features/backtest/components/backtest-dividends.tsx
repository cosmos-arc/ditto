import type { BacktestDividendStatement } from "../types";

const money = (value: number) => value.toLocaleString("zh-CN", { maximumFractionDigits: 6 });
const unit = (assetClass: string | undefined) => (assetClass === "etf" ? "份" : "股");
const entryAssetClass = (statement: BacktestDividendStatement, eventId: string) =>
	statement.events.find((event) => event.eventId === eventId)?.assetClass ??
	(statement.conversions.some((conversion) => conversion.eventId === eventId) ? "etf" : undefined);
const labels: Record<string, string> = {
	receivable: "除息应收",
	cash_payment: "分红到账",
	tax_reserved: "预留补税",
	tax_payment: "税款扣付",
	share_credit: "送转计入总份额",
	share_release: "送转股份上市可卖",
	share_tax_payment: "送股初始扣税",
	share_conversion: "份额折算（数量重标定）",
};

export function BacktestDividends({ statement }: { readonly statement: BacktestDividendStatement | null | undefined }) {
	if (!statement)
		return <p className="mb-3 text-xs text-(--color-foreground-secondary)">本报告没有已保存的分红与送转事件。</p>;
	return (
		<details className="mb-3 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-3 text-xs">
			<summary className="cursor-pointer rounded-(--radius-sm) font-medium focus-visible:outline-2 focus-visible:outline-offset-4">
				分红与送转账本（{statement.events.length + statement.conversions.length} 个事件）
			</summary>
			<p className="my-3">{statement.policy}</p>
			<p>金额单位：人民币元（CNY）；日期：交易所当地日期。净资产 = 现金 + 应收 + 持仓市值 − 待扣税款。</p>
			{statement.conversions.map((conversion) => (
				<details key={conversion.eventId} className="my-3">
					<summary className="cursor-pointer focus-visible:outline-2">
						{conversion.symbol} · 份额折算 1 折 {money(conversion.ratio)} · 生效 {conversion.effective}
					</summary>
					<p>
						实施公告 {conversion.announcement}；除权生效 {conversion.effective}。生效日开盘前总份额与可卖份额 ×
						{money(conversion.ratio)}，总成本不变、平均成本重摊；无现金与税，当日净资产不变。
					</p>
					<p className="break-all">取整说明：{conversion.roundingNote}</p>
					<p className="break-all">来源：{conversion.source}</p>
				</details>
			))}
			{statement.events.map((event) => (
				<details key={event.eventId} className="my-3">
					<summary className="cursor-pointer focus-visible:outline-2">
						{event.symbol} · 登记 {event.record} · {event.quantity} {unit(event.assetClass)} · 税前每
						{unit(event.assetClass)} {money(event.grossPerShare)} 元
					</summary>
					<p>
						实施公告 {event.announcement}；除息 {event.ex}；派息 {event.pay ?? "无现金分派"}。
					</p>
					{event.shareRatio > 0 && (
						<>
							<p>
								每股送转 {money(event.shareRatio)} 股；新增股份上市 {event.listing}；每原股送转应税所得{" "}
								{money(event.taxableShareIncome)} 元。
							</p>
							<p className="break-all">送转税务依据：{event.shareTaxBasis}</p>
						</>
					)}
					<p className="break-all">来源：{event.source}</p>
				</details>
			))}
			<ul aria-label="分红与税款流水" className="my-3">
				{statement.entries.map((entry) => (
					<li key={`${entry.eventId}-${entry.day}-${entry.kind}-${entry.acquired}`}>
						{entry.day} · {labels[entry.kind]} · {money(entry.amount)} 元
						{entry.quantity ? ` · ${entry.quantity} ${unit(entryAssetClass(statement, entry.eventId))}` : ""}
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
				<table aria-label="持仓每日份额与成本" className="mt-3 w-full whitespace-nowrap text-left font-data">
					<thead>
						<tr>
							{[
								"日期",
								"证券",
								"总份额（股/份）",
								"可卖（股/份）",
								"未可卖（股/份）",
								"平均成本（元/股或份）",
								"总成本（元）",
							].map((label) => (
								<th key={label} scope="col" className="p-2">
									{label}
								</th>
							))}
						</tr>
					</thead>
					<tbody>
						{statement.balances.flatMap((row) =>
							row.positions.map((position) => (
								<tr key={`${row.day}-${position.instrumentId}`}>
									<th scope="row" className="p-2">
										{row.day}
									</th>
									<td className="p-2">{position.symbol}</td>
									<td className="p-2">{position.quantity}</td>
									<td className="p-2">{position.availableQuantity}</td>
									<td className="p-2">{position.lockedQuantity}</td>
									<td className="p-2">{money(position.averageCost)}</td>
									<td className="p-2">{money(position.totalCost)}</td>
								</tr>
							)),
						)}
					</tbody>
				</table>
			</section>
		</details>
	);
}
