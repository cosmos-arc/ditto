import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { fetchBacktestRequest, retryBacktestRun } from "../api/backtests";
import { backtestKeys } from "../hooks/use-backtest-resources";
import type { BacktestRun } from "../types";

const purposes: Readonly<Record<string, string>> = {
	historical_reconstruction: "普通历史重建（历史可得性未认证）",
	limited_historical_research: "受限历史研究",
	strict_snapshot_replay: "严格快照重放请求（资格以原证据为准）",
	unclassified: "旧请求未记录用途",
};
const statuses: Readonly<Record<string, string>> = {
	ready: "输入预检通过；运行结果以运行状态为准",
	blocked: "输入预检未通过",
	pending: "等待冻结与预检",
	unrecorded: "未记录冻结预检",
};

export function BacktestRequestPanel({ run }: { readonly run: BacktestRun }) {
	const recoverable = run.status === "failed" || run.status === "cancelled";
	const [open, setOpen] = useState(recoverable);
	const [storageError, setStorageError] = useState("");
	const storageKey = `ditto:backtest-recovery:${run.runId}`;
	const [savedRun, setSavedRun] = useState(() => {
		try {
			return new URLSearchParams(sessionStorage.getItem(storageKey) ?? "").get("runId") ?? "";
		} catch {
			return "";
		}
	});
	const query = useQuery({
		queryKey: [...backtestKeys.run(run.runId), "request"],
		queryFn: () => fetchBacktestRequest(run.runId),
		enabled: open,
		refetchInterval: open && ["pending", "running"].includes(run.status) ? 2000 : false,
	});
	const retry = useMutation({
		mutationFn: retryBacktestRun,
		onSuccess: ({ runId }) => {
			setSavedRun(runId);
			try {
				const saved = new URLSearchParams(sessionStorage.getItem(storageKey) ?? "");
				saved.set("runId", runId);
				sessionStorage.setItem(storageKey, saved.toString());
			} catch {
				setStorageError("新运行已创建，但浏览器未保存入口；请保存下方链接。");
			}
		},
	});
	const request = query.data;
	return (
		<details
			open={open}
			onToggle={(event) => setOpen(event.currentTarget.open)}
			className="shrink-0 border-b border-(--color-border-subtle) px-4 py-2 text-xs"
		>
			<summary className="cursor-pointer font-medium">请求与冻结来源</summary>
			{/* biome-ignore lint/a11y/noNoninteractiveTabindex: The bounded source ledger must be keyboard-scrollable even when a completed run has no action buttons. */}
			<section aria-label="请求与来源明细" tabIndex={0} className="mt-2 max-h-64 space-y-2 overflow-y-auto">
				{query.isLoading ? <p role="status">正在重开请求…</p> : null}
				{query.error ? (
					<div role="alert">
						{query.error.message}{" "}
						<Button size="sm" variant="outline" onClick={() => void query.refetch()}>
							重试请求读取
						</Button>
					</div>
				) : null}
				{request ? (
					<>
						<p>
							{purposes[request.purpose] ?? request.purpose} · {statuses[request.inputStatus]}
						</p>
						<p>
							请求区间 {request.startDate ?? "未记录"} → {request.endDate ?? "未记录"} · 初始资金{" "}
							{request.initialCash?.toLocaleString("zh-CN") ?? "未记录"} 元（CNY）
						</p>
						<p>
							证券池 {request.universe || "未记录"} · 冻结证券 {request.members.join("、") || "尚未解析"}
						</p>
						{request.frozenAt ? <p>本次冻结时刻 {request.frozenAt}（含时区）</p> : null}
						{request.reason || run.errorMessage ? <p role="alert">{request.reason || run.errorMessage}</p> : null}
						{request.limitations.map((text) => (
							<p key={text}>{text}</p>
						))}
						{request.sources.length ? (
							<ul className="space-y-2">
								{request.sources.map((source) => (
									<li key={source.snapshotId} className="break-all">
										{source.source} / {source.dataset} · 业务请求区间 {source.startDate} → {source.endDate} ·
										{source.rows.toLocaleString("zh-CN")} 行 · {source.verified ? "载荷校验通过" : "载荷未通过校验"}
										<p>
											实际入库 {source.receivedAt} · 最近观察 {source.observedAt}（含时区）
										</p>
										<p>
											来源身份 {source.snapshotId} · 校验值 {source.checksum}
										</p>
									</li>
								))}
							</ul>
						) : (
							<p>尚无已保存的冻结来源。</p>
						)}
						{recoverable ? (
							<div className="space-y-2">
								<p>补齐上方证据后，沿原证券池、策略版本、日期和资金创建新运行；本次请求与报告保留。</p>
								{savedRun ? (
									<a className="underline" href={`/research/backtests/${encodeURIComponent(savedRun)}`}>
										打开补证后的新运行
									</a>
								) : (
									<Button
										size="sm"
										disabled={retry.isPending}
										onClick={() => {
											try {
												const saved = new URLSearchParams(sessionStorage.getItem(storageKey) ?? "");
												const key = saved.get("key") || crypto.randomUUID();
												saved.set("key", key);
												sessionStorage.setItem(storageKey, saved.toString());
												setStorageError("");
												retry.mutate({ runId: run.runId, idempotencyKey: key });
											} catch {
												setStorageError("无法保存恢复请求，请恢复浏览器存储后重试。");
											}
										}}
									>
										{retry.isPending ? "正在恢复…" : "补证后沿原配置新建运行"}
									</Button>
								)}
								{retry.error ? <p role="alert">{retry.error.message}；再次点击将核对同一次恢复。</p> : null}
								{storageError ? <p role="alert">{storageError}</p> : null}
							</div>
						) : null}
					</>
				) : null}
			</section>
		</details>
	);
}
