import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fetchETFAllocationReview, listETFAllocationVersions } from "../api/etf-allocations";
import { fetchManualAccountLedger, fetchManualAccounts } from "../api/manual-accounts";
import { fetchPaperAccountLedger, fetchPaperAccounts } from "../api/paper-accounts";
import { tradingKeys } from "../api/query-keys";

function selection() {
	const query = new URLSearchParams(window.location.search);
	return {
		versionId: query.get("etfVersion") ?? "",
		account: query.get("etfReviewAccount") ?? "",
		asOf: query.get("etfReviewAsOf") ?? localCutoff(new Date().toISOString()).slice(0, 10),
		// Offset-bearing instant: the cutoff is PIT identity, so the URL must
		// survive reopening in a browser with a different timezone.
		cutoff: query.get("etfReviewCutoff") ?? new Date().toISOString(),
		priceSnapshots: query.get("etfReviewPriceSnapshots") ?? "",
	};
}

function localCutoff(instant: string): string {
	const date = new Date(instant);
	if (Number.isNaN(date.getTime())) return "";
	return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 23);
}

export function ETFAllocationReview({
	allocationId,
	onContextChange,
}: {
	readonly allocationId: string;
	readonly onContextChange?: (context: { versionId: string; account: string }) => void;
}) {
	const [selected, setSelected] = useState(selection);
	useEffect(() => {
		const restore = () => {
			const next = selection();
			setSelected(next);
			onContextChange?.({ versionId: next.versionId, account: next.account });
		};
		window.addEventListener("popstate", restore);
		return () => window.removeEventListener("popstate", restore);
	}, [onContextChange]);
	const choose = (field: keyof ReturnType<typeof selection>, value: string) => {
		const next = { ...selected, [field]: value };
		const url = new URL(window.location.href);
		url.searchParams.set("etfVersion", next.versionId);
		if (next.account) url.searchParams.set("etfReviewAccount", next.account);
		else url.searchParams.delete("etfReviewAccount");
		url.searchParams.set("etfReviewAsOf", next.asOf);
		url.searchParams.set("etfReviewCutoff", next.cutoff);
		if (next.priceSnapshots) url.searchParams.set("etfReviewPriceSnapshots", next.priceSnapshots);
		else url.searchParams.delete("etfReviewPriceSnapshots");
		if (field === "versionId" || field === "account") {
			url.searchParams.delete("historyComparison");
			url.searchParams.delete("historyComparisonVersion");
			url.searchParams.delete("historyComparisonAccount");
		}
		window.history.pushState(window.history.state, "", url);
		setSelected(next);
		if (field === "versionId" || field === "account")
			onContextChange?.({ versionId: next.versionId, account: next.account });
	};
	const versions = useQuery({
		queryKey: ["etf-allocation-versions", allocationId],
		queryFn: () => listETFAllocationVersions(allocationId),
	});
	const paperAccounts = useQuery({ queryKey: tradingKeys.paperAccounts(), queryFn: fetchPaperAccounts });
	const manualAccounts = useQuery({ queryKey: tradingKeys.manualAccounts(), queryFn: fetchManualAccounts });
	const version = versions.data?.find((item) => item.versionId === selected.versionId);
	const separator = selected.account.indexOf(":");
	const kind = selected.account.slice(0, separator);
	const accountId = separator > 0 ? selected.account.slice(separator + 1) : "";
	const accountKnown =
		(kind === "paper" && paperAccounts.data?.some((item) => item.account_id === accountId)) ||
		(kind === "manual" && manualAccounts.data?.some((item) => item.account_id === accountId));
	const cutoffTime = new Date(selected.cutoff).getTime();
	const cutoffInstant = Number.isNaN(cutoffTime) ? null : new Date(cutoffTime).toISOString();
	const ledger = useQuery({
		// The fallback ledger read is bound to the same knowledge cutoff as the
		// valuation; without recorded_through it would show later-recorded
		// corrections as the account's actual state and contradict the review.
		queryKey: ["etf-review-ledger", kind, accountId, selected.asOf, cutoffInstant],
		queryFn: async () =>
			kind === "paper"
				? await fetchPaperAccountLedger(accountId, selected.asOf, cutoffInstant ?? undefined)
				: await fetchManualAccountLedger(accountId, selected.asOf, cutoffInstant ?? undefined),
		enabled: Boolean(version && accountKnown && /^\d{4}-\d{2}-\d{2}$/u.test(selected.asOf) && cutoffInstant),
		retry: false,
	});
	const snapshot = ledger.data?.snapshot;
	const snapshotIds = selected.priceSnapshots
		.split(",")
		.map((item) => item.trim())
		.filter(Boolean);
	const valuation = useQuery({
		queryKey: [
			"etf-review-valuation",
			allocationId,
			selected.versionId,
			kind,
			accountId,
			selected.asOf,
			cutoffInstant,
			snapshotIds,
		],
		queryFn: () =>
			fetchETFAllocationReview(allocationId, selected.versionId, {
				account_kind: kind as "paper" | "manual",
				account_id: accountId,
				as_of: selected.asOf,
				knowledge_cutoff: cutoffInstant ?? "",
				source_snapshot_ids: snapshotIds,
			}),
		enabled: Boolean(version && accountKnown && snapshotIds.length && cutoffInstant),
		retry: false,
	});
	return (
		<section aria-label="ETF 配置复盘" className="space-y-3 rounded border border-(--color-border-subtle) p-4">
			<h2 className="font-semibold">ETF 配置复盘</h2>
			<p>配置 {allocationId} · 研究目标仅来自所选版本；账户实际仅来自所选账本。</p>
			{versions.isLoading && <p>正在读取配置版本…</p>}
			{versions.isError && (
				<button type="button" onClick={() => void versions.refetch()}>
					版本读取失败，重试
				</button>
			)}
			<label className="block">
				配置版本{" "}
				<select
					aria-label="复盘配置版本"
					value={selected.versionId}
					onChange={(event) => choose("versionId", event.target.value)}
				>
					<option value="">选择版本</option>
					{versions.data?.map((item) => (
						<option key={item.versionId} value={item.versionId}>
							{item.createdAt} · {item.versionId}
						</option>
					))}
				</select>
			</label>
			{versions.data && !version && selected.versionId && <p role="alert">所选配置版本不存在。</p>}
			{version && (
				<div>
					<p>
						研究配置 · {version.asof} · 快照 {version.sourceSnapshotId} · 审查 {version.reviewStatus}
					</p>
					<p>目标现金比例 {version.cashWeight}</p>
					<ul>
						{Object.entries(version.weights).map(([id, weight]) => (
							<li key={id}>
								ETF #{id}：目标 {weight}
							</li>
						))}
					</ul>
					<p>
						已知同指数目标暴露：
						{Object.entries(version.trackingExposure)
							.map(([index, weight]) => `${index} ${weight}`)
							.join("；") || "未知"}
					</p>
					<p>其他工具的穿透重叠：未知；不按名称推断。</p>
				</div>
			)}
			<label className="block">
				账户{" "}
				<select
					aria-label="复盘账户"
					value={selected.account}
					onChange={(event) => choose("account", event.target.value)}
				>
					<option value="">选择账户</option>
					{paperAccounts.data?.map((item) => (
						<option key={`paper:${item.account_id}`} value={`paper:${item.account_id}`}>
							Paper · {item.account_name}
						</option>
					))}
					{manualAccounts.data?.map((item) => (
						<option key={`manual:${item.account_id}`} value={`manual:${item.account_id}`}>
							Manual · {item.account_name}
						</option>
					))}
				</select>
			</label>
			{paperAccounts.isError && (
				<button type="button" onClick={() => void paperAccounts.refetch()}>
					Paper 账户读取失败，重试
				</button>
			)}
			{manualAccounts.isError && (
				<button type="button" onClick={() => void manualAccounts.refetch()}>
					Manual 账户读取失败，重试
				</button>
			)}
			<label className="block">
				账本日期{" "}
				<input
					aria-label="复盘账本日期"
					type="date"
					value={selected.asOf}
					onChange={(event) => choose("asOf", event.target.value)}
				/>
			</label>
			<label className="block">
				估值知识截止{" "}
				<input
					aria-label="复盘知识截止"
					type="datetime-local"
					step={0.001}
					value={localCutoff(selected.cutoff)}
					onChange={(event) => {
						// datetime-local yields an offset-less local string; store the
						// resolved instant so the URL keeps the exact PIT cutoff.
						const instant = new Date(event.target.value);
						if (!Number.isNaN(instant.getTime())) choose("cutoff", instant.toISOString());
					}}
				/>
			</label>
			<label className="block">
				价格快照 ID（多个用逗号分隔）{" "}
				<input
					aria-label="复盘价格快照"
					value={selected.priceSnapshots}
					onChange={(event) => choose("priceSnapshots", event.target.value)}
				/>
			</label>
			{!snapshotIds.length && <p>未选择价格快照，以下仅显示账本单时点，无法计算实际权重和差异。</p>}
			{valuation.isLoading && <p>正在核对估值证据…</p>}
			{valuation.isError && (
				<p role="alert">
					估值失败：{String(valuation.error)}；
					<button type="button" onClick={() => void valuation.refetch()}>
						重试
					</button>
					。账本单时点仍可查看。
				</p>
			)}
			{valuation.data && (
				<section aria-label="ETF 目标与实际估值">
					<p>
						估值快照 {valuation.data.valuationSnapshotId} · 账本 {valuation.data.ledgerHash}
					</p>
					<p>
						目标现金 {valuation.data.targetCashWeight}；实际现金 {valuation.data.actualCashWeight}；现金差异{" "}
						{valuation.data.cashDriftBps} bps
					</p>
					<ul>
						{valuation.data.positions.map((item) => (
							<li key={item.instrumentId}>
								ETF #{item.instrumentId}：目标 {item.targetWeight}；实际 {item.actualWeight}；差异 {item.driftBps} bps
							</li>
						))}
					</ul>
					<p>
						已知同指数实际暴露：
						{Object.entries(valuation.data.actualExposure)
							.map(([index, weight]) => `${index} ${weight}`)
							.join("；") || "未知"}
					</p>
					<p>
						指数归属未知的实际持仓：{valuation.data.unknownExposureInstrumentIds.join("、") || "无"}
						；其他穿透重叠仍未知。
					</p>
				</section>
			)}
			{selected.account && !accountKnown && !paperAccounts.isLoading && !manualAccounts.isLoading && (
				<p role="alert">所选账户不存在或暂不可读取。</p>
			)}
			{ledger.isError && (
				<button type="button" onClick={() => void ledger.refetch()}>
					账本读取失败，重试
				</button>
			)}
			{ledger.isLoading && <p>正在读取账户账本…</p>}
			{snapshot && (
				<div>
					<p>
						{kind === "paper" ? "Paper 模拟成交账本" : "Manual 用户记录账本"} · {snapshot.as_of} ·{" "}
						{snapshot.ledger_hash}
					</p>
					<p>
						实际现金 {snapshot.cash.total} CNY；账户总值{" "}
						{snapshot.valuation_complete ? `${snapshot.total_value} CNY` : "估值不完整"}
					</p>
					<ul>
						{snapshot.positions.map((position) => (
							<li key={position.instrument_id}>
								#{position.instrument_id}：实际 {position.quantity} 份；市值{" "}
								{snapshot.valuation_complete ? `${position.market_value} CNY` : "缺价格证据"}
							</li>
						))}
					</ul>
					<p>
						{snapshot.valuation_complete
							? "目标与实际来自不同来源；账户持仓由账本重建。"
							: "缺少同日价格证据，无法计算实际权重或目标差异；不以目标权重代替实际持仓。"}
					</p>
					<p>上方账本按交易日与所选知识截止重建，与估值共用同一 PIT 截止；缺价格快照时市值与实际权重仍不可得。</p>
				</div>
			)}
			<p>历史曲线需要 Model 目标工件、Paper/Manual 账本、共同有效估值点和独立价格快照；当前配置目标不会回填历史。</p>
			<a
				href={`/markets?${new URLSearchParams({ etfAllocation: allocationId, etfVersion: selected.versionId, etfAsof: version?.asof ?? "", etfCutoff: version ? localCutoff(version.knowledgeCutoff) : "", etfSnapshot: version?.sourceSnapshotId ?? "" }).toString()}`}
			>
				返回 ETF 配置
			</a>
		</section>
	);
}
