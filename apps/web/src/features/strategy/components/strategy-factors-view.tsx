import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useStrategy } from "../hooks/use-strategy";

interface StrategyFactorsViewProps {
	readonly id: string;
}

function StrategyFactorsViewContent({ id }: StrategyFactorsViewProps) {
	const { data, isLoading, isError } = useStrategy(id);

	if (isLoading) return <LoadingSkeleton />;
	if (isError || !data) throw new Error("Failed to load strategy factors");

	return (
		<div className="p-3">
			<section
				aria-label="因子配置"
				className="overflow-hidden rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2)"
			>
				<header className="flex items-center justify-between border-b border-(--color-border-subtle) px-4 py-3">
					<div>
						<h2 className="text-sm font-semibold text-(--color-foreground)">因子配置</h2>
						<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
							来自当前服务端策略 spec；诊断证据请进入因子分析并绑定完整 PIT 范围。
						</p>
					</div>
					<span className="font-data text-xs text-(--color-foreground-tertiary)">
						{data.spec.signalExpressions.length} 项
					</span>
				</header>
				{data.spec.signalExpressions.length > 0 ? (
					<table aria-label="策略因子" className="w-full border-collapse text-left text-xs">
						<thead className="bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
							<tr>
								<th className="px-4 py-2 font-medium">Factor ID</th>
								<th className="w-28 px-3 py-2 text-right font-medium">权重</th>
								<th className="w-28 px-3 py-2 text-right font-medium">诊断</th>
							</tr>
						</thead>
						<tbody className="divide-y divide-(--color-border-subtle)">
							{data.spec.signalExpressions.map((factor, index) => (
								<tr key={factor}>
									<td className="px-4 py-3 font-data text-(--color-foreground)">{factor}</td>
									<td className="px-3 py-3 text-right font-data text-(--color-foreground-secondary)">
										{data.spec.signalWeights[index] ?? "—"}
									</td>
									<td className="px-3 py-3 text-right">
										<a
											href={`/research/factors/${encodeURIComponent(factor)}`}
											aria-label={`分析 ${factor}`}
											className="text-(--color-accent) hover:underline"
										>
											打开分析
										</a>
									</td>
								</tr>
							))}
						</tbody>
					</table>
				) : (
					<p className="p-4 text-sm text-(--color-foreground-tertiary)">当前策略未定义 signal expression。</p>
				)}
			</section>
		</div>
	);
}

export function StrategyFactorsView(props: StrategyFactorsViewProps) {
	return (
		<DittoErrorBoundary>
			<StrategyFactorsViewContent {...props} />
		</DittoErrorBoundary>
	);
}
