import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { BacktestListPage, createBacktestRun } from "@/features/backtest";
import { useStrategies } from "@/features/strategy";

export function BacktestCatalogPage() {
	return <BacktestListPage createForm={<BacktestCreateForm />} />;
}

function BacktestCreateForm() {
	const strategies = useStrategies();
	const queryClient = useQueryClient();
	const [strategyId, setStrategyId] = useState("");
	const [startDate, setStartDate] = useState("");
	const [endDate, setEndDate] = useState("");
	const [initialCash, setInitialCash] = useState("1000000");
	const [allowExperimental, setAllowExperimental] = useState(false);
	const submit = useMutation({
		mutationFn: createBacktestRun,
		onSuccess: () => queryClient.invalidateQueries({ queryKey: ["backtests", "runs"] }),
	});
	const published = (strategies.data ?? []).filter((entry) => entry.lifecycleState === "published");
	const fieldClass = "mt-1 w-full rounded-(--radius-sm) border border-(--color-border) bg-(--color-surface-app) p-2";
	return (
		<form
			className="space-y-4 text-sm"
			onSubmit={(event) => {
				event.preventDefault();
				if (!submit.isPending && !submit.isSuccess && startDate <= endDate) {
					submit.mutate({ strategyId, startDate, endDate, initialCash: Number(initialCash), allowExperimental });
				}
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
			<fieldset disabled={submit.isPending || submit.isSuccess} className="space-y-4">
				<label className="block">
					策略
					<select
						className={fieldClass}
						value={strategyId}
						onChange={(event) => setStrategyId(event.currentTarget.value)}
						required
					>
						<option value="">{strategies.isLoading ? "正在加载策略…" : "选择已发布策略"}</option>
						{published.map((entry) => (
							<option key={entry.strategyId} value={entry.strategyId}>
								{entry.name} · v{entry.version}
							</option>
						))}
					</select>
				</label>
				{!strategies.isLoading && !strategies.error && published.length === 0 ? (
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
				<Button type="submit" disabled={!strategyId || strategies.isError || strategies.isLoading}>
					{submit.isPending ? "正在提交…" : "提交回测"}
				</Button>
			</fieldset>
			{submit.error ? (
				<p role="alert" className="text-(--color-led-danger)">
					{submit.error.message}
				</p>
			) : null}
			{submit.data ? (
				<p role="status">
					已提交，等待执行。
					<a className="underline" href={`/research/backtests/${encodeURIComponent(submit.data.runId)}`}>
						查看本次回测
					</a>
				</p>
			) : null}
		</form>
	);
}
