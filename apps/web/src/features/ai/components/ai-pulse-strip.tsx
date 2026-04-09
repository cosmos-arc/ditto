import { Metric } from "@/components/data/metric";
import { useAiPulse } from "../hooks";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function AiPulseStrip() {
	const { data, isLoading, isError, refetch } = useAiPulse();

	if (isLoading) {
		return (
			<div className="grid grid-cols-3 gap-3 p-4">
				{Array.from({ length: 3 }).map((_, i) => (
					<LoadingSkeleton key={i} variant="metric" />
				))}
			</div>
		);
	}

	return (
		<DittoErrorBoundary
			fallbackProps={{
				title: "AI 脉动数据加载失败",
				onRetry: () => void refetch(),
			}}
		>
			<div className="grid grid-cols-3 gap-3 p-4">
				<Metric
					label="运行中计划"
					value={data?.runningPlans ?? "—"}
					sub="活跃执行"
				/>
				<Metric
					label="待审批"
					value={data?.pendingApprovals ?? "—"}
					sub="等待确认"
				/>
				<Metric
					label="Copilot 会话"
					value={data?.activeCopilotSessions ?? "—"}
					sub="进行中对话"
				/>
			</div>
		</DittoErrorBoundary>
	);
}
