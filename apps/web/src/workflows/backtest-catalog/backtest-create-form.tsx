import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { createBacktestRun } from "@/features/backtest";
import { useStrategies, useStrategyVersions } from "@/features/strategy";

interface BacktestCreateFormProps {
	readonly strategyId?: string;
	readonly version?: number;
}

export function BacktestCreateForm({ strategyId: initialStrategyId = "", version = 0 }: BacktestCreateFormProps) {
	const storageKey = `ditto:backtest-draft:${initialStrategyId || "catalog"}`;
	const [saved, setSaved] = useState(() => {
		try {
			return new URLSearchParams(sessionStorage.getItem(storageKey) ?? "");
		} catch {
			return new URLSearchParams();
		}
	});
	const strategies = useStrategies();
	const queryClient = useQueryClient();
	const [strategyId, setStrategyId] = useState(initialStrategyId || saved.get("strategyId") || "");
	const [strategyVersion, setStrategyVersion] = useState(Number(saved.get("strategyVersion") ?? version));
	const versions = useStrategyVersions(strategyId);
	const [startDate, setStartDate] = useState(saved.get("startDate") ?? "");
	const [endDate, setEndDate] = useState(saved.get("endDate") ?? "");
	const [initialCash, setInitialCash] = useState(saved.get("initialCash") ?? "1000000");
	const [allowExperimental, setAllowExperimental] = useState(saved.get("allowExperimental") === "true");
	const [historicalReconstruction, setHistoricalReconstruction] = useState(
		saved.get("historicalReconstruction") === "true",
	);
	const [storageError, setStorageError] = useState("");
	const submit = useMutation({
		mutationFn: createBacktestRun,
		onSuccess: (result, input) => {
			try {
				const receipt = new URLSearchParams(sessionStorage.getItem(storageKey) ?? "");
				if (receipt.get("key") === input.idempotencyKey) {
					receipt.set("runId", result.runId);
					persist(receipt);
				}
			} catch {
				setStorageError("本次回测已创建，但浏览器无法保存入口；请从回测列表查找。");
			}
			void queryClient.invalidateQueries({ queryKey: ["backtests", "runs"] });
		},
	});
	function persist(value: URLSearchParams): boolean {
		try {
			sessionStorage.setItem(storageKey, value.toString());
			setSaved(value);
			setStorageError("");
			return true;
		} catch {
			setStorageError("无法保存本次提交记录，请恢复浏览器存储后重试。");
			return false;
		}
	}
	const runId = submit.data?.runId ?? saved.get("runId");
	const published = (strategies.data ?? []).filter((entry) => entry.lifecycleState === "published");
	const fieldClass = "mt-1 w-full rounded-(--radius-sm) border border-(--color-border) bg-(--color-surface-app) p-2";
	return (
		<form
			className="space-y-4 text-sm"
			onSubmit={(event) => {
				event.preventDefault();
				if (
					submit.isPending ||
					runId ||
					startDate > endDate ||
					!Number.isSafeInteger(strategyVersion) ||
					strategyVersion <= 0
				)
					return;
				const input = {
					strategyId,
					strategyVersion,
					startDate,
					endDate,
					initialCash: Number(initialCash),
					allowExperimental,
					...(historicalReconstruction ? { historicalReconstruction: true } : {}),
				};
				const fingerprint = JSON.stringify(input);
				const key = saved.get("fingerprint") === fingerprint ? saved.get("key") : null;
				const idempotencyKey = key || crypto.randomUUID();
				const attempt = new URLSearchParams({
					strategyId,
					strategyVersion: String(strategyVersion),
					startDate,
					endDate,
					initialCash,
					allowExperimental: String(allowExperimental),
					historicalReconstruction: String(historicalReconstruction),
					fingerprint,
					key: idempotencyKey,
				});
				if (persist(attempt)) submit.mutate({ ...input, idempotencyKey });
			}}
		>
			<p className="text-xs text-(--color-foreground-secondary)">
				受限历史研究，严格历史未认证。使用起始日固定样本，可能存在选择及存活者偏差；不自动启用信号或 Paper。
			</p>
			{strategies.error ? (
				<div role="alert">
					{strategies.error.message}{" "}
					<Button type="button" variant="outline" onClick={() => void strategies.refetch()}>
						重试策略目录
					</Button>
				</div>
			) : null}
			<fieldset disabled={submit.isPending || Boolean(runId)} className="space-y-4">
				<label className="block">
					历史请求用途
					<select
						className={fieldClass}
						value={historicalReconstruction ? "reconstruction" : "limited"}
						onChange={(event) => setHistoricalReconstruction(event.target.value === "reconstruction")}
					>
						<option value="limited">受限历史研究 · 当前存储读取</option>
						<option value="reconstruction">普通历史重建 · 冻结留存事实</option>
					</select>
				</label>
				<p className="text-xs text-(--color-foreground-secondary)">
					普通历史重建保留真实入库时间，按业务／公告日期过滤；缺证会保存原因，补证后可沿原配置创建新运行。
					严格快照重放需要另外的已认证研究快照，本入口不授予该资格。
				</p>
				<label className="block">
					策略
					<select
						className={fieldClass}
						value={strategyId}
						disabled={Boolean(initialStrategyId)}
						onChange={(event) => {
							const next = event.currentTarget.value;
							setStrategyId(next);
							setStrategyVersion(published.find((entry) => entry.strategyId === next)?.version ?? 0);
						}}
						required
					>
						{initialStrategyId ? <option value={initialStrategyId}>{initialStrategyId}</option> : null}
						<option value="">{strategies.isLoading ? "正在加载策略…" : "选择已发布策略"}</option>
						{published
							.filter((entry) => entry.strategyId !== initialStrategyId)
							.map((entry) => (
								<option key={entry.strategyId} value={entry.strategyId}>
									{entry.name} · v{entry.version}
								</option>
							))}
					</select>
				</label>
				<label className="block">
					策略版本
					<select
						className={fieldClass}
						value={strategyVersion || ""}
						required
						onChange={(event) => setStrategyVersion(Number(event.currentTarget.value))}
					>
						<option value="">选择明确版本</option>
						{strategyVersion > 0 && !versions.data?.some((entry) => entry.version === strategyVersion) ? (
							<option value={strategyVersion}>v{strategyVersion}</option>
						) : null}
						{(versions.data ?? []).map((entry) => (
							<option key={entry.version} value={entry.version}>
								v{entry.version} · {entry.lifecycleState}
							</option>
						))}
					</select>
				</label>
				{versions.error ? (
					<p role="alert">
						版本目录加载失败；已选版本保持不变。
						<Button type="button" variant="outline" onClick={() => void versions.refetch()}>
							重试版本目录
						</Button>
					</p>
				) : null}
				{!initialStrategyId && !strategies.isLoading && !strategies.error && published.length === 0 ? (
					<p>尚无已发布策略，请先在策略目录完成发布。</p>
				) : null}
				<label className="block">
					开始日期
					<input
						type="date"
						className={fieldClass}
						value={startDate}
						max={endDate || undefined}
						onChange={(event) => setStartDate(event.currentTarget.value)}
						required
					/>
				</label>
				<label className="block">
					结束日期
					<input
						type="date"
						className={fieldClass}
						value={endDate}
						min={startDate || undefined}
						onChange={(event) => setEndDate(event.currentTarget.value)}
						required
					/>
				</label>
				<label className="block">
					初始资金（元）
					<input
						type="number"
						className={fieldClass}
						min="0.01"
						step="0.01"
						value={initialCash}
						onChange={(event) => setInitialCash(event.currentTarget.value)}
						required
					/>
				</label>
				<label className="flex items-center gap-2">
					<input
						type="checkbox"
						checked={allowExperimental}
						onChange={(event) => setAllowExperimental(event.currentTarget.checked)}
					/>
					允许实验数据
				</label>
				<p className="text-xs text-(--color-foreground-secondary)">
					允许实验数据仅对本次研究生效，不代表历史认证或真实交易资格。
				</p>
				<Button
					type="submit"
					disabled={
						!strategyId || strategyVersion <= 0 || (!initialStrategyId && (strategies.isError || strategies.isLoading))
					}
				>
					{submit.isPending ? "正在提交…" : "提交回测"}
				</Button>
			</fieldset>
			{storageError ? <p role="alert">{storageError}</p> : null}
			{submit.error ? (
				<p role="alert" className="text-(--color-led-danger)">
					{submit.error.message}
				</p>
			) : null}
			{runId ? (
				<p role="status">
					本次回测已创建，状态以运行详情为准。
					<a className="underline" href={`/research/backtests/${encodeURIComponent(runId)}`}>
						查看本次回测
					</a>
				</p>
			) : null}
			{runId ? (
				<Button
					type="button"
					variant="outline"
					onClick={() => {
						if (persist(new URLSearchParams())) submit.reset();
					}}
				>
					开始另一回测
				</Button>
			) : null}
			<p className="text-xs text-(--color-foreground-secondary)">
				失败后输入保留；本标签页刷新或返回后可找回提交。关闭标签页后请从回测列表查找。
			</p>
		</form>
	);
}
