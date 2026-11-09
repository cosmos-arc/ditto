import type { BacktestFeeStatement } from "../types";

const money = (value: number) => value.toLocaleString("zh-CN", { maximumFractionDigits: 6 });

export function BacktestFeeStatementView({
	statement,
}: {
	readonly statement: BacktestFeeStatement | null | undefined;
}) {
	if (!statement) return <p className="mb-3 text-xs text-(--color-foreground-secondary)">本报告未保存逐笔费用账单。</p>;
	return (
		<details className="mb-3 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-3 text-xs">
			<summary className="cursor-pointer rounded-(--radius-sm) font-medium focus-visible:outline-2 focus-visible:outline-offset-4">
				逐笔费用账单（{statement.fills.length} 笔）
			</summary>
			<p className="my-3 text-(--color-foreground-secondary)">{statement.policy}</p>
			<p className="mb-3">
				人民币元（CNY），展示至多 6 位小数，导出保留原值。期末现金：
				{statement.finalCash === null ? "未记录" : money(statement.finalCash)} 元。规则核对日：
				{statement.rulesObservedAt}。
			</p>
			{statement.fills.length === 0 ? (
				<p>本次运行没有实际成交。</p>
			) : (
				// biome-ignore lint/a11y/noNoninteractiveTabindex: keyboard users must be able to scroll this wide bill horizontally.
				<section className="overflow-x-auto" aria-label="逐笔费用账单滚动区域" tabIndex={0}>
					<table aria-label="逐笔费用账单" className="w-full whitespace-nowrap text-left font-data">
						<thead>
							<tr>
								{[
									"日期 / 标的",
									"方向 / 数量（股或份）",
									"成交价（元）",
									"佣金（元）",
									"印花税（元）",
									"过户费（元）",
									"合计（元）",
									"采用费率",
								].map((label) => (
									<th key={label} scope="col" className="p-2">
										{label}
									</th>
								))}
							</tr>
						</thead>
						<tbody>
							{statement.fills.map((fill) => (
								<tr key={fill.fillId} className="border-t border-(--color-border-subtle)">
									<td className="p-2">
										{fill.tradeDate}
										<br />
										{fill.symbol}
									</td>
									<td className="p-2">
										{fill.direction === "buy" ? "买入" : "卖出"} / {fill.quantity}
									</td>
									{[fill.price, fill.commission, fill.stampDuty, fill.transferFee, fill.totalFee].map(
										(value, index) => (
											<td key={["price", "commission", "stamp", "transfer", "total"][index]} className="p-2">
												{money(value)}
											</td>
										),
									)}
									<td className="p-2">
										<details>
											<summary className="cursor-pointer">{fill.schedule.asOfDate} 起</summary>
											<p>
												佣金 {fill.schedule.commissionRate}，最低 {fill.schedule.minCommission} 元/笔
											</p>
											<p>卖出印花税 {fill.schedule.stampDutyRate}</p>
											<p>
												过户费 {fill.schedule.transferFeeRate} × 成交金额 + {fill.schedule.transferFeePerShare} 元 ×
												股数
											</p>
										</details>
									</td>
								</tr>
							))}
						</tbody>
					</table>
				</section>
			)}
		</details>
	);
}
