import { useState } from "react";
import { ContextSection } from "@/components/domain";
import { useCapitalProfile, useInstrumentDetail } from "../hooks/use-instrument-workspace";

// 上海日(chart view 同款 +8h 偏移,correctness F7)。
function dateDaysAgo(days: number): string {
	const shanghaiNow = Date.now() + 8 * 3600 * 1000;
	return new Date(shanghaiNow - days * 86400 * 1000).toISOString().slice(0, 10);
}

type CapitalProfile = {
	readonly window: { readonly start: string; readonly end: string };
	readonly moneyflow: {
		readonly rows: ReadonlyArray<{ readonly trade_date: string; readonly net_mf_amount: number | null }>;
		readonly latest_trade_date: string | null;
		readonly data_coverage: CoverageInfo | null;
	};
	readonly top_list: {
		readonly rows: ReadonlyArray<{
			readonly trade_date: string;
			readonly reason: string;
			readonly net_amount: number | null;
		}>;
		readonly latest_trade_date: string | null;
		readonly data_coverage: CoverageInfo | null;
	};
	readonly top_inst: {
		readonly rows: ReadonlyArray<{
			readonly trade_date: string;
			readonly exalter: string;
			readonly side: string | null;
			readonly buy: number | null;
			readonly sell: number | null;
		}>;
		readonly latest_trade_date: string | null;
		readonly data_coverage: CoverageInfo | null;
	};
	readonly margin_trading: {
		readonly rows: ReadonlyArray<{
			readonly trade_date: string;
			readonly margin_buy_balance: number | null;
		}>;
		readonly latest_trade_date: string | null;
		readonly pending_trade_dates: readonly string[];
		readonly freshness_promise: string;
		readonly read_error: string | null;
		readonly data_coverage: CoverageInfo | null;
	};
};

type CoverageInfo = {
	readonly dataset: string;
	readonly status: string;
	readonly measured_end: string | null;
	readonly gaps: readonly string[];
};

function coverageTitle(coverage: CoverageInfo | null): string | undefined {
	if (!coverage) return undefined;
	return `${coverage.dataset} 覆盖 ${coverage.measured_end ?? "—"}（${coverage.status}）`;
}

function BlockShell({
	title,
	latest,
	coverage,
	children,
}: {
	title: string;
	latest: string | null;
	coverage: CoverageInfo | null;
	children: React.ReactNode;
}) {
	return (
		<section className="min-w-0 flex-1 basis-72" data-info-unit={`capital-block-${title}`}>
			<header className="flex items-baseline justify-between gap-2 border-b border-(--color-border-subtle) px-3 py-2">
				<h3 className="text-sm font-medium text-(--color-foreground)">{title}</h3>
				<span className="text-xs text-(--color-foreground-tertiary)" title={coverageTitle(coverage) ?? ""}>
					末端 {latest ?? "—"}
				</span>
			</header>
			<div className="max-h-72 overflow-auto p-3 text-xs leading-5 text-(--color-foreground-secondary)">{children}</div>
		</section>
	);
}

export function InstrumentCapitalView({ id }: { readonly id: string }) {
	const [startDate, setStartDate] = useState(() => dateDaysAgo(30));
	const [endDate, setEndDate] = useState(() => dateDaysAgo(0));
	const [includeExperimental, setIncludeExperimental] = useState(true);
	const detail = useInstrumentDetail(id);
	const assetClass = detail.data?.asset_class;
	const query = useCapitalProfile(id, {
		startDate,
		endDate,
		allowExperimental: includeExperimental,
	});
	const profile = query.data as CapitalProfile | undefined;
	// 资金面四数据集均为沪深个股数据集:其他资产类显式不适用(correctness F5)。
	const notApplicable = assetClass != null && assetClass !== "stock";

	return (
		<div className="p-[var(--density-panel-padding)]">
			<ContextSection title="资金画像">
				<div
					className="flex flex-wrap items-center gap-4 border-b border-(--color-border-subtle) p-3 text-xs text-(--color-foreground-tertiary)"
					data-info-unit="capital-profile-toolbar"
				>
					<span>最新观察 · 业务日期窗内现在已知的数据</span>
					<button
						type="button"
						disabled={query.isFetching || !includeExperimental || notApplicable}
						onClick={() => void query.refetch()}
						className="rounded-md border border-(--color-border-primary) px-2 py-1 disabled:opacity-50"
					>
						刷新资金画像
					</button>
					<label className="flex items-center gap-1.5">
						<input
							type="checkbox"
							checked={includeExperimental}
							onChange={(event) => setIncludeExperimental(event.currentTarget.checked)}
							data-testid="capital-experimental-toggle"
						/>
						含 experimental 数据（资金画像四数据集均 experimental）
					</label>
					<label className="grid gap-1">
						开始日期
						<input
							type="date"
							value={startDate}
							onChange={(event) => setStartDate(event.currentTarget.value)}
							className="rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1.5 text-sm text-(--color-foreground)"
						/>
					</label>
					<label className="grid gap-1">
						截至日期
						<input
							type="date"
							value={endDate}
							onChange={(event) => setEndDate(event.currentTarget.value)}
							className="rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1.5 text-sm text-(--color-foreground)"
						/>
					</label>
				</div>

				{notApplicable && (
					<p className="p-3 text-xs text-(--color-foreground-muted)" data-testid="capital-not-applicable">
						资金面数据不适用于该资产类({assetClass})——四数据集均为沪深个股数据集。
					</p>
				)}
				{!notApplicable && !includeExperimental && (
					<p className="p-3 text-xs text-(--color-foreground-muted)" data-testid="capital-experimental-required">
						资金画像四数据集均 experimental——勾选「含 experimental 数据」后展示。
					</p>
				)}
				{!notApplicable && includeExperimental && query.isLoading && (
					<p className="p-3 text-xs text-(--color-foreground-tertiary)">读取资金画像中</p>
				)}
				{query.isError && (
					<p className="p-3 text-xs text-(--color-foreground-muted)" data-testid="capital-profile-error">
						资金画像不可用：{String(query.error)}
					</p>
				)}
				{!notApplicable && includeExperimental && profile && (
					<div className="flex flex-wrap">
						<BlockShell
							title="逐日资金流"
							latest={profile.moneyflow.latest_trade_date}
							coverage={profile.moneyflow.data_coverage}
						>
							{profile.moneyflow.rows.length === 0 ? (
								<p>窗口内无资金流行（正常空或数据未覆盖）。</p>
							) : (
								<table className="w-full">
									<tbody>
										{profile.moneyflow.rows.map((row) => (
											<tr key={row.trade_date} className="font-data">
												<td className="pr-3 text-(--color-foreground-tertiary)">{row.trade_date}</td>
												<td className="text-right">
													净流入 {row.net_mf_amount == null ? "—" : `${row.net_mf_amount.toFixed(1)} 万元`}
												</td>
											</tr>
										))}
									</tbody>
								</table>
							)}
						</BlockShell>
						<BlockShell
							title="龙虎榜"
							latest={profile.top_list.latest_trade_date}
							coverage={profile.top_list.data_coverage}
						>
							{profile.top_list.rows.length === 0 ? (
								<p>窗口内无上榜事件（无事件≠漏页）。</p>
							) : (
								<ul className="grid gap-1.5">
									{profile.top_list.rows.map((row) => (
										<li key={`${row.trade_date}-${row.reason}`}>
											<span className="font-data text-(--color-foreground-tertiary)">{row.trade_date}</span>{" "}
											{row.reason} · 净买入 {row.net_amount == null ? "—" : `${(row.net_amount / 1e8).toFixed(2)} 亿元`}
										</li>
									))}
								</ul>
							)}
						</BlockShell>
						<BlockShell
							title="龙虎榜席位"
							latest={profile.top_inst.latest_trade_date}
							coverage={profile.top_inst.data_coverage}
						>
							{profile.top_inst.rows.length === 0 ? (
								<p>窗口内无席位明细（席位≠机构总仓位）。</p>
							) : (
								<ul className="grid gap-1.5">
									{profile.top_inst.rows.map((row) => (
										<li key={`${row.trade_date}-${row.exalter}-${row.side ?? "?"}`}>
											<span className="font-data text-(--color-foreground-tertiary)">{row.trade_date}</span>{" "}
											{row.side === "0" ? "买" : "卖"} · {row.exalter}
										</li>
									))}
								</ul>
							)}
						</BlockShell>
						<BlockShell
							title="两融"
							latest={profile.margin_trading.latest_trade_date}
							coverage={profile.margin_trading.data_coverage}
						>
							<p className="text-(--color-foreground-tertiary)">{profile.margin_trading.freshness_promise}</p>
							{profile.margin_trading.read_error && (
								<p data-testid="capital-margin-error">两融块读取失败(受限展示):{profile.margin_trading.read_error}</p>
							)}
							{profile.margin_trading.pending_trade_dates.length > 0 && (
								<p data-testid="capital-margin-pending">
									待补交易日：{profile.margin_trading.pending_trade_dates.join("、")}
								</p>
							)}
							{profile.margin_trading.rows.length === 0 ? (
								<p>窗口内无两融行（非两融标的或不覆盖）。</p>
							) : (
								<table className="mt-1.5 w-full">
									<tbody>
										{profile.margin_trading.rows.slice(0, 10).map((row) => (
											<tr key={row.trade_date} className="font-data">
												<td className="pr-3 text-(--color-foreground-tertiary)">{row.trade_date}</td>
												<td className="text-right">
													融资余额{" "}
													{row.margin_buy_balance == null ? "—" : `${(row.margin_buy_balance / 1e8).toFixed(2)} 亿元`}
												</td>
											</tr>
										))}
									</tbody>
								</table>
							)}
						</BlockShell>
					</div>
				)}
			</ContextSection>
		</div>
	);
}
