import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useFactorDetail } from "../hooks";

const RESULT_STYLE: Record<string, string> = {
	pass: "bg-green-600",
	warning: "bg-yellow-600",
	fail: "bg-red-600",
};

const ATTR_LABELS: Record<string, string> = {
	ic: "IC",
	ir: "IR",
	decay: "衰减",
	turnover: "换手率",
	coverage: "覆盖率",
};

function formatAttrValue(key: string, value: number): string {
	switch (key) {
		case "ic":
			return value.toFixed(3);
		case "ir":
			return value.toFixed(2);
		case "coverage":
			return `${(value * 100).toFixed(0)}%`;
		default:
			return String(value);
	}
}

interface FactorOverviewProps {
	readonly id: string;
}

export function FactorOverview({ id }: FactorOverviewProps) {
	const { data, isLoading, refetch } = useFactorDetail(id);

	if (isLoading) {
		return <LoadingSkeleton variant="table" rows={6} />;
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{data && (
				<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
					<div data-info-level="l2" data-info-unit="factor-attributes">
						<ContextSection title="因子属性">
							<dl className="grid grid-cols-2 gap-2">
								{(
									[
										["ic", data.factor.ic],
										["ir", data.factor.ir],
										["decay", data.factor.decay],
										["turnover", data.factor.turnover],
										["coverage", data.factor.coverage],
									] as const
								).map(([key, value]) => (
									<div
										key={key}
										className="flex justify-between hover:bg-(--color-interaction-hover-subtle-bg) rounded px-2 py-1"
									>
										<dt className="text-(--color-foreground-tertiary)">{ATTR_LABELS[key]}</dt>
										<dd>{formatAttrValue(key, value)}</dd>
									</div>
								))}
							</dl>
						</ContextSection>
					</div>

					<div data-info-level="l2" data-info-unit="factor-diagnostics">
						<ContextSection title="诊断检查">
							<div className="mb-2 text-sm">
								{(() => {
									const counts = data.diagnostics.reduce(
										(acc, d) => {
											acc[d.result] = (acc[d.result] ?? 0) + 1;
											return acc;
										},
										{} as Record<string, number>,
									);
									const parts = [
										counts.pass ? `${counts.pass} pass` : null,
										counts.warning ? `${counts.warning} warning` : null,
										counts.fail ? `${counts.fail} fail` : null,
									].filter(Boolean);
									return parts.join(", ");
								})()}
							</div>
							<ul className="flex flex-col gap-1">
								{data.diagnostics.map((diag) => (
									<li
										key={diag.name}
										data-info-level="l3"
										data-info-unit="diagnostic-item"
										className="flex items-center justify-between hover:bg-(--color-interaction-hover-subtle-bg) rounded px-2 py-1"
									>
										<span className="flex items-center gap-2">
											<span className={`inline-block size-2 rounded-full ${RESULT_STYLE[diag.result]}`} />
											{diag.name}
										</span>
										<span className="text-(--color-foreground-tertiary)">
											{diag.value} vs {diag.threshold}
										</span>
									</li>
								))}
							</ul>
						</ContextSection>
					</div>
				</div>
			)}
		</DittoErrorBoundary>
	);
}
