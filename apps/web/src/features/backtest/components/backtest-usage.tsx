import { type BacktestReport, legacyBacktestUsage } from "../types";

export function BacktestUsage({ report }: { readonly report: BacktestReport | undefined }) {
	const scope = report?.usageContext ?? legacyBacktestUsage;
	return (
		<aside
			aria-label="回测使用边界"
			className="shrink-0 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2 text-xs"
		>
			<p className="font-medium text-(--color-risk-warning-fg)">
				{scope.intendedUse === "research_protocol" ? "严格研究流程产物（资格另验）" : "受限历史研究"}
				{" · 严格历史可得性未认证"}
			</p>
			<p className="mt-1 text-(--color-foreground-secondary)">
				完成仅表示执行结束；结果不自动授予策略晋级、信号启用或 Paper 授权。
			</p>
			<details className="mt-1">
				<summary className="cursor-pointer text-(--color-foreground-secondary)">样本范围、来源与已知限制</summary>
				<div className="mt-2 max-h-48 space-y-2 overflow-auto text-(--color-foreground-secondary)">
					<p>
						实际区间：{report?.periodStart || "未记录"} → {report?.periodEnd || "未记录"}
					</p>
					<p>
						{scope.samplePool === "recorded_input_union"
							? `实际输入标的集合：${scope.inputInstrumentIds.join("、") || "未记录"}；不代表历史全市场。`
							: "样本池语义未记录；不能推定为历史全市场。"}
					</p>
					<ul className="list-inside list-disc">
						{scope.limitations.map((limitation) => (
							<li key={limitation}>{limitation}</li>
						))}
					</ul>
					<p>原报告策略版本、来源与成本记录：</p>
					<pre className="whitespace-pre-wrap break-all font-data">
						{JSON.stringify(report?.strategyPromotion ?? "未记录", null, 2)}
					</pre>
					<p>原报告时间守卫（不代表来源认证）：</p>
					<pre className="whitespace-pre-wrap break-all font-data">
						{JSON.stringify(report?.pitPolicy ?? "未记录", null, 2)}
					</pre>
				</div>
			</details>
		</aside>
	);
}
