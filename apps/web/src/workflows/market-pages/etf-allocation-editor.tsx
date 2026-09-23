import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { ETFCandidate } from "@/features/instruments";
import { listETFAllocationVersions, saveETFAllocationVersion } from "@/features/portfolio";

type Props = {
	readonly items: readonly ETFCandidate[];
	readonly asof: string;
	readonly cutoff: string;
	readonly cutoffInput: string;
	readonly snapshot: string;
};

function savedIdentity(): { allocationId: string; versionId: string } {
	const query = new URLSearchParams(window.location.search);
	return { allocationId: query.get("etfAllocation") ?? "", versionId: query.get("etfVersion") ?? "" };
}

export function ETFAllocationEditor({ items, asof, cutoff, cutoffInput, snapshot }: Props) {
	const initial = savedIdentity();
	const [allocationId, setAllocationId] = useState(initial.allocationId);
	const [versionId, setVersionId] = useState(initial.versionId);
	const [selected, setSelected] = useState<number[]>([]);
	const [mode, setMode] = useState<"equal" | "manual">("equal");
	const [cashWeight, setCashWeight] = useState("0.2");
	const [maxWeight, setMaxWeight] = useState("0.5");
	const [manualWeights, setManualWeights] = useState<Record<number, string>>({});
	const [reason, setReason] = useState("");
	const retry = useRef<{ body: string; key: string } | null>(null);
	const generatedId = useRef(`etf-${crypto.randomUUID()}`);
	const restoredVersion = useRef("");
	const queryClient = useQueryClient();
	const versions = useQuery({
		queryKey: ["etf-allocation-versions", allocationId],
		queryFn: () => listETFAllocationVersions(allocationId),
		enabled: Boolean(allocationId),
	});
	const saved = versions.data?.find((item) => item.versionId === versionId);
	useEffect(() => {
		if (!saved || restoredVersion.current === saved.versionId) return;
		restoredVersion.current = saved.versionId;
		setSelected(Object.keys(saved.weights).map(Number));
		setMode(saved.mode === "manual" ? "manual" : "equal");
		setCashWeight(saved.cashWeight);
		setMaxWeight(saved.maxPositionWeight);
		setManualWeights(Object.fromEntries(Object.entries(saved.weights).map(([id, weight]) => [Number(id), weight])));
		setReason(saved.reason);
	}, [saved]);
	const save = useMutation({
		mutationFn: async () => {
			const id = allocationId.trim() || generatedId.current;
			const body = {
				parent_version_id: versionId || null,
				asof,
				knowledge_cutoff: cutoff,
				source_snapshot_id: snapshot,
				instrument_ids: selected,
				mode,
				cash_weight: cashWeight,
				max_position_weight: maxWeight,
				manual_weights:
					mode === "manual"
						? Object.fromEntries(selected.map((item) => [String(item), manualWeights[item] ?? ""]))
						: {},
				reason: reason.trim(),
			};
			const fingerprint = JSON.stringify([id, body]);
			if (retry.current?.body !== fingerprint) retry.current = { body: fingerprint, key: crypto.randomUUID() };
			return saveETFAllocationVersion(id, retry.current.key, body);
		},
		onSuccess: (result) => {
			setAllocationId(result.allocationId);
			setVersionId(result.versionId);
			const url = new URL(window.location.href);
			url.searchParams.set("etfAllocation", result.allocationId);
			url.searchParams.set("etfVersion", result.versionId);
			url.searchParams.set("etfAsof", asof);
			url.searchParams.set("etfCutoff", cutoffInput);
			url.searchParams.set("etfSnapshot", snapshot);
			window.history.replaceState(null, "", url);
			void queryClient.invalidateQueries({ queryKey: ["etf-allocation-versions", result.allocationId] });
		},
	});
	const unchanged =
		saved &&
		saved.asof === asof &&
		new Date(saved.knowledgeCutoff).getTime() === new Date(cutoff).getTime() &&
		saved.sourceSnapshotId === snapshot &&
		saved.mode === mode &&
		Number(saved.cashWeight) === Number(cashWeight) &&
		Number(saved.maxPositionWeight) === Number(maxWeight) &&
		saved.reason === reason.trim() &&
		selected.length === Object.keys(saved.weights).length &&
		selected.every((id) =>
			mode === "manual" ? Number(saved.weights[id]) === Number(manualWeights[id]) : id in saved.weights,
		);
	const canSave =
		Boolean(snapshot && cutoff && asof && selected.length && reason.trim()) && !save.isPending && !unchanged;
	return (
		<section aria-label="ETF 配置" className="space-y-3 rounded border border-(--color-border-subtle) p-3">
			<h3 className="font-medium">保存研究配置</h3>
			<p>保存仅生成研究候选；Paper 需要合格数据、策略晋级和独立审批，Manual 账本不会随保存改变。</p>
			<label>
				配置名称{" "}
				<input
					aria-label="配置名称"
					value={allocationId}
					onChange={(event) => {
						setAllocationId(event.target.value);
						setVersionId("");
					}}
					placeholder="留空自动生成"
				/>
			</label>
			{versions.isError && (
				<button type="button" onClick={() => void versions.refetch()}>
					版本读取失败，重试
				</button>
			)}
			{versions.isLoading && <p>正在读取已保存版本…</p>}
			{versions.data && (
				<label>
					已保存版本{" "}
					<select aria-label="已保存版本" value={versionId} onChange={(event) => setVersionId(event.target.value)}>
						<option value="">新配置</option>
						{versions.data.map((item) => (
							<option key={item.versionId} value={item.versionId}>
								{item.createdAt} · {item.versionId.slice(-8)}
							</option>
						))}
					</select>
				</label>
			)}
			<fieldset>
				<legend>选择 ETF 工具</legend>
				{items.map((item) => (
					<label key={item.instrumentId} className="block">
						<input
							type="checkbox"
							checked={selected.includes(item.instrumentId)}
							onChange={(event) =>
								setSelected((current) =>
									event.target.checked
										? [...current, item.instrumentId]
										: current.filter((id) => id !== item.instrumentId),
								)
							}
						/>{" "}
						{item.name} · {item.ticker}
					</label>
				))}
			</fieldset>
			<label>
				权重模式{" "}
				<select
					aria-label="权重模式"
					value={mode}
					onChange={(event) => setMode(event.target.value as "equal" | "manual")}
				>
					<option value="equal">等权</option>
					<option value="manual">手工</option>
				</select>
			</label>
			<label>
				现金比例{" "}
				<input
					aria-label="现金比例"
					type="number"
					min="0"
					max="1"
					step="0.00000001"
					value={cashWeight}
					onChange={(event) => setCashWeight(event.target.value)}
				/>
			</label>
			<label>
				单仓上限{" "}
				<input
					aria-label="单仓上限"
					type="number"
					min="0"
					max="1"
					step="0.00000001"
					value={maxWeight}
					onChange={(event) => setMaxWeight(event.target.value)}
				/>
			</label>
			{mode === "manual" &&
				selected.map((id) => (
					<label key={id} className="block">
						ETF {id} 权重{" "}
						<input
							aria-label={`ETF ${id} 权重`}
							type="number"
							min="0"
							max="1"
							step="0.00000001"
							value={manualWeights[id] ?? ""}
							onChange={(event) => setManualWeights((current) => ({ ...current, [id]: event.target.value }))}
						/>
					</label>
				))}
			<label className="block">
				配置理由 <input aria-label="配置理由" value={reason} onChange={(event) => setReason(event.target.value)} />
			</label>
			<button type="button" disabled={!canSave} onClick={() => save.mutate()}>
				{save.isPending ? "保存中…" : "保存候选版本"}
			</button>
			{save.isError && <p role="alert">保存失败：{String(save.error)}</p>}
			{saved && (
				<div>
					<p>
						已保存 {saved.versionId} · {saved.paperStatus} · 规则 {saved.ruleVersion}
					</p>
					<p>
						现金 {saved.cashWeight}；同指数暴露{" "}
						{Object.entries(saved.trackingExposure)
							.map(([key, weight]) => `${key}: ${weight}`)
							.join("，") || "未知"}
					</p>
					<p>
						目标权重{" "}
						{Object.entries(saved.weights)
							.map(([key, weight]) => `${key}: ${weight}`)
							.join("，")}
					</p>
				</div>
			)}
		</section>
	);
}
