import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ContextSection } from "@/components/domain/context-section";
import { type ETFField, fetchETFCandidates, fetchETFReferenceSnapshots } from "@/features/instruments";

const FIELD_LABELS = [
	["tracking_index", "跟踪指数"],
	["asset_class", "资产类别"],
	["fund_currency", "基金币种"],
	["trading_currency", "交易币种"],
	["management_fee", "管理费"],
	["custody_fee", "托管费"],
	["aum", "规模"],
	["daily_amount", "20 日成交额中位数"],
	["trading_restriction", "交易限制"],
	["distribution", "分红"],
	["price_close", "原始收盘价"],
	["nav", "最近已披露 NAV"],
	["iopv", "IOPV"],
] as const;

function FieldValue({ field }: { readonly field: ETFField | undefined }) {
	if (!field || field.value === null) {
		return (
			<span title={field?.missing_reason ?? "no_qualified_observation"}>
				缺失（{field?.missing_reason ?? "无合格观测"}）
			</span>
		);
	}
	return (
		<span>
			{field.value} {field.unit}
		</span>
	);
}

export function ETFCandidates() {
	const today = new Date().toISOString().slice(0, 10);
	const [asof, setAsof] = useState(today);
	const [cutoff, setCutoff] = useState(`${today}T23:59:59`);
	const [snapshot, setSnapshot] = useState("");
	const [exposure, setExposure] = useState("");
	const [search, setSearch] = useState("");
	const [sortField, setSortField] = useState("ticker");
	const cutoffDate = new Date(cutoff);
	const cutoffUTC = Number.isNaN(cutoffDate.getTime()) ? "" : `${cutoffDate.toISOString().slice(0, 19)}Z`;
	const snapshots = useQuery({
		queryKey: ["etf-reference-snapshots", cutoffUTC],
		queryFn: () => fetchETFReferenceSnapshots(cutoffUTC),
		enabled: Boolean(cutoffUTC),
	});
	const candidates = useQuery({
		queryKey: ["etf-candidates", asof, cutoffUTC, snapshot, exposure, search, sortField],
		queryFn: () =>
			fetchETFCandidates({ asof, cutoff: cutoffUTC, sourceSnapshotId: snapshot, exposure, search, sortField }),
		enabled: Boolean(asof && cutoffUTC && snapshot),
	});
	const exposureCatalog = useQuery({
		queryKey: ["etf-exposure-catalog", asof, cutoffUTC, snapshot],
		queryFn: () => fetchETFCandidates({ asof, cutoff: cutoffUTC, sourceSnapshotId: snapshot }),
		enabled: Boolean(asof && cutoffUTC && snapshot),
	});
	const items = candidates.data ?? [];
	const exposures = [
		...new Set(
			(exposureCatalog.data ?? [])
				.map((item) => item.fields["tracking_index"]?.value)
				.filter((value): value is string => typeof value === "string"),
		),
	];

	return (
		<ContextSection title="ETF 暴露与工具比较" data-info-level="l2" data-info-unit="etf-candidates">
			<div className="space-y-4 p-3 text-sm">
				<p className="text-(--color-foreground-tertiary)">
					只读参考比较。字段资格尚未验证，正式研究与交易仍需独立准入；名称和活跃状态来自当前目录。市价与 NAV
					可异步，不能视为实时溢价。
				</p>
				<div className="flex flex-wrap gap-3">
					<label>
						研究日期{" "}
						<input aria-label="研究日期" type="date" value={asof} onChange={(event) => setAsof(event.target.value)} />
					</label>
					<label>
						知识截止{" "}
						<input
							aria-label="知识截止"
							type="datetime-local"
							value={cutoff}
							onChange={(event) => setCutoff(event.target.value)}
						/>
					</label>
					<label>
						来源快照{" "}
						<select aria-label="来源快照" value={snapshot} onChange={(event) => setSnapshot(event.target.value)}>
							<option value="">选择快照</option>
							{snapshots.data?.map((id) => (
								<option key={id} value={id}>
									{id}
								</option>
							))}
						</select>
					</label>
					<label>
						指数暴露{" "}
						<input
							aria-label="指数暴露"
							value={exposure}
							onChange={(event) => setExposure(event.target.value)}
							list="etf-exposures"
							placeholder="指数标识"
						/>
					</label>
					<datalist id="etf-exposures">
						{exposures.map((id) => (
							<option key={id} value={id} />
						))}
					</datalist>
					<label>
						代码或名称{" "}
						<input aria-label="代码或名称" value={search} onChange={(event) => setSearch(event.target.value)} />
					</label>
					<label>
						排序{" "}
						<select aria-label="排序" value={sortField} onChange={(event) => setSortField(event.target.value)}>
							<option value="ticker">代码</option>
							<option value="management_fee">管理费</option>
							<option value="custody_fee">托管费</option>
							<option value="aum">规模</option>
							<option value="daily_amount">20 日成交额</option>
						</select>
					</label>
				</div>
				{snapshots.isError && (
					<button type="button" onClick={() => void snapshots.refetch()}>
						快照加载失败，重试
					</button>
				)}
				{snapshots.data?.length === 0 && <p>没有已披露的 ETF 参考快照。</p>}
				{candidates.isError && (
					<button type="button" onClick={() => void candidates.refetch()}>
						比较失败，重试
					</button>
				)}
				{snapshot && candidates.isLoading && <p>正在读取候选…</p>}
				{snapshot && candidates.isSuccess && items.length === 0 && <p>该条件下没有 ETF 候选或合格暴露关系。</p>}
				{items.map((item) => (
					<details key={item.instrument_id} className="rounded border border-(--color-border-subtle) p-3">
						<summary className="cursor-pointer font-medium">
							{item.name} · {item.ticker} · {item.fields["tracking_index"]?.value ?? "暴露未知"} ·{" "}
							{item.is_active ? "上市" : "不可投资"}
						</summary>
						<a href={`/instruments/${item.instrument_id}`} className="text-(--color-accent)">
							查看标的详情
						</a>
						<dl className="mt-3 grid gap-2 sm:grid-cols-2">
							{FIELD_LABELS.map(([key, label]) => {
								const field = item.fields[key];
								return (
									<div key={key} className="rounded bg-(--color-surface-1) p-2">
										<dt className="text-(--color-foreground-tertiary)">{label}</dt>
										<dd>
											<FieldValue field={field} />
										</dd>
										<p className="text-xs text-(--color-foreground-tertiary)">
											{field?.observed_on ?? "日期未知"} · 披露 {field?.published_at ?? "未知"} ·{" "}
											{field?.source ?? "来源未知"} · {field?.eligibility ?? "资格未知"}
											{field?.sample_count == null ? "" : ` · ${field.sample_count}/20 日`}
										</p>
										<p className="break-all text-xs text-(--color-foreground-tertiary)">
											快照 {field?.source_snapshot_id ?? "未知"} · 有效期 {field?.effective_from ?? "未知"} 至{" "}
											{field?.effective_to ?? "开放"}
										</p>
									</div>
								);
							})}
						</dl>
					</details>
				))}
			</div>
		</ContextSection>
	);
}
