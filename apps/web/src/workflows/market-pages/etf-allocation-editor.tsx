import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { ETFCandidate } from "@/features/instruments";
import { listETFAllocationVersions, reviewETFAllocationVersion, saveETFAllocationVersion } from "@/features/portfolio";

type Props = {
	readonly items: readonly ETFCandidate[];
	readonly asof: string;
	readonly cutoff: string;
	readonly cutoffInput: string;
	readonly snapshot: string;
};

type SaveBody = Parameters<typeof saveETFAllocationVersion>[2];
type PendingSave = { id: string; key: string; fingerprint: string; body: SaveBody };
type ReviewAction = "submit" | "approve" | "reject";
type PendingReview = { fingerprint: string; key: string };

function savedIdentity(): { allocationId: string; versionId: string } {
	const query = new URLSearchParams(window.location.search);
	return { allocationId: query.get("etfAllocation") ?? "", versionId: query.get("etfVersion") ?? "" };
}

function pendingSave(): PendingSave | null {
	const state: unknown = window.history.state;
	const pending =
		state && typeof state === "object" ? (state as Record<string, unknown>)["etfAllocationPending"] : null;
	if (!pending || typeof pending !== "object") return null;
	const value = pending as Partial<PendingSave>;
	return typeof value.id === "string" &&
		typeof value.key === "string" &&
		typeof value.fingerprint === "string" &&
		value.body &&
		typeof value.body === "object"
		? (value as PendingSave)
		: null;
}

function pendingReview(): PendingReview | null {
	const state: unknown = window.history.state;
	const pending =
		state && typeof state === "object" ? (state as Record<string, unknown>)["etfAllocationReviewPending"] : null;
	if (!pending || typeof pending !== "object") return null;
	const value = pending as Partial<PendingReview>;
	return typeof value.fingerprint === "string" && typeof value.key === "string" ? (value as PendingReview) : null;
}

export function ETFAllocationEditor({ items, asof, cutoff, cutoffInput, snapshot }: Props) {
	const initial = savedIdentity();
	const pending = useRef(pendingSave()).current;
	const [allocationId, setAllocationId] = useState(pending?.id ?? initial.allocationId);
	const [versionId, setVersionId] = useState(pending?.body.parent_version_id ?? initial.versionId);
	const [selected, setSelected] = useState<number[]>(pending?.body.instrument_ids ?? []);
	const [mode, setMode] = useState<"equal" | "manual">(pending?.body.mode ?? "equal");
	const [cashWeight, setCashWeight] = useState(String(pending?.body.cash_weight ?? "0.2"));
	const [maxWeight, setMaxWeight] = useState(String(pending?.body.max_position_weight ?? "0.5"));
	const [manualWeights, setManualWeights] = useState<Record<number, string>>(
		Object.fromEntries(
			Object.entries(pending?.body.manual_weights ?? {}).map(([id, weight]) => [Number(id), String(weight)]),
		),
	);
	const [reason, setReason] = useState(pending?.body.reason ?? "");
	const [reviewActor, setReviewActor] = useState("");
	const [reviewReason, setReviewReason] = useState("");
	const [confirmingReject, setConfirmingReject] = useState(false);
	const reviewRetry = useRef<PendingReview | null>(pendingReview());
	const retry = useRef<{ body: string; key: string } | null>(
		pending ? { body: pending.fingerprint, key: pending.key } : null,
	);
	const generatedId = useRef(pending?.id ?? `etf-${crypto.randomUUID()}`);
	const restoredVersion = useRef(pending?.body.parent_version_id ?? "");
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
			const url = new URL(window.location.href);
			url.searchParams.set("etfAllocation", id);
			url.searchParams.set("etfAsof", asof);
			url.searchParams.set("etfCutoff", cutoffInput);
			url.searchParams.set("etfSnapshot", snapshot);
			const state = window.history.state && typeof window.history.state === "object" ? window.history.state : {};
			window.history.replaceState(
				{ ...state, etfAllocationPending: { id, key: retry.current.key, fingerprint, body } },
				"",
				url,
			);
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
			const state: Record<string, unknown> =
				window.history.state && typeof window.history.state === "object" ? { ...window.history.state } : {};
			delete state["etfAllocationPending"];
			window.history.replaceState(state, "", url);
			void queryClient.invalidateQueries({ queryKey: ["etf-allocation-versions", result.allocationId] });
		},
	});
	const review = useMutation({
		mutationFn: (action: ReviewAction) => {
			if (!saved) throw new Error("请先选择已保存版本");
			const body = { action, actor: reviewActor.trim(), reason: reviewReason.trim() };
			const fingerprint = JSON.stringify([allocationId, saved.versionId, body]);
			if (reviewRetry.current?.fingerprint !== fingerprint) {
				reviewRetry.current = { fingerprint, key: crypto.randomUUID() };
			}
			const state = window.history.state && typeof window.history.state === "object" ? window.history.state : {};
			window.history.replaceState({ ...state, etfAllocationReviewPending: reviewRetry.current }, "");
			return reviewETFAllocationVersion(allocationId, saved.versionId, reviewRetry.current.key, body);
		},
		onSuccess: (result) => {
			queryClient.setQueryData<Awaited<ReturnType<typeof listETFAllocationVersions>>>(
				["etf-allocation-versions", result.allocationId],
				(current) => current?.map((item) => (item.versionId === result.versionId ? result : item)),
			);
			const state: Record<string, unknown> =
				window.history.state && typeof window.history.state === "object" ? { ...window.history.state } : {};
			delete state["etfAllocationReviewPending"];
			window.history.replaceState(state, "");
			reviewRetry.current = null;
			setConfirmingReject(false);
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
			<p>
				保存仅生成研究候选；审查批准只确认精确版本，Paper 还需单独校验交易资格。保存或批准不会改变 Paper、Manual 账本。
			</p>
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
					<select
						aria-label="已保存版本"
						value={versionId}
						onChange={(event) => {
							setVersionId(event.target.value);
							setConfirmingReject(false);
						}}
					>
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
					<p>研究审查结果不授权 Paper 执行。</p>
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
					{["research_only", "review_pending"].includes(saved.paperStatus) && (
						<div className="space-y-2">
							<label className="block">
								审查人{" "}
								<input
									aria-label="审查人"
									value={reviewActor}
									onChange={(event) => setReviewActor(event.target.value)}
								/>
							</label>
							<label className="block">
								审查理由{" "}
								<input
									aria-label="审查理由"
									value={reviewReason}
									onChange={(event) => setReviewReason(event.target.value)}
								/>
							</label>
							{saved.paperStatus === "research_only" ? (
								<button
									type="button"
									disabled={!reviewActor.trim() || !reviewReason.trim() || review.isPending}
									onClick={() => review.mutate("submit")}
								>
									提交审查
								</button>
							) : (
								<>
									<button
										type="button"
										disabled={!reviewActor.trim() || !reviewReason.trim() || review.isPending}
										onClick={() => review.mutate("approve")}
									>
										研究审查通过
									</button>
									{confirmingReject ? (
										<>
											<span>拒绝后该版本不可再审查。</span>
											<button
												type="button"
												disabled={!reviewActor.trim() || !reviewReason.trim() || review.isPending}
												onClick={() => review.mutate("reject")}
											>
												确认拒绝
											</button>
											<button type="button" onClick={() => setConfirmingReject(false)}>
												取消
											</button>
										</>
									) : (
										<button
											type="button"
											disabled={!reviewActor.trim() || !reviewReason.trim() || review.isPending}
											onClick={() => setConfirmingReject(true)}
										>
											拒绝此版本
										</button>
									)}
								</>
							)}
						</div>
					)}
					{review.isError && <p role="alert">审查失败：{String(review.error)}</p>}
				</div>
			)}
		</section>
	);
}
