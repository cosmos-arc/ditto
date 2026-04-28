import { useAiPulse } from "../hooks";
import { DittoErrorBoundary } from "@/lib/error-boundary";

function Separator() {
	return (
		<span
			className="h-3 w-px bg-(--color-border-subtle)"
			aria-hidden="true"
		/>
	);
}

export function AiPulseStrip() {
	const { data, isLoading, refetch } = useAiPulse();

	if (isLoading) {
		return (
			<div
				data-slot="pulse-strip"
				data-testid="pulse-strip"
				className="flex items-center h-8 px-4 gap-4 bg-(--color-surface-strip) border-b border-(--color-border-subtle)"
			>
				{Array.from({ length: 3 }).map((_, i) => (
					<div
						key={i}
						className="h-3 w-24 animate-pulse rounded bg-(--color-surface-2)"
					/>
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
			<div
				data-slot="pulse-strip"
				data-testid="pulse-strip"
				className="flex items-center h-8 px-4 gap-4 bg-(--color-surface-strip) border-b border-(--color-border-subtle)"
			>
				<span className="flex items-center gap-1.5 text-xs text-(--color-foreground-secondary)">
					<span className="size-1.5 rounded-full bg-(--color-accent) animate-pulse" />
					{data?.runningPlans ?? "—"} 个运行中计划
				</span>
				<Separator />
				<span className="text-xs text-(--color-foreground-secondary)">
					{data?.pendingApprovals ?? "—"} 项待审批
				</span>
				<Separator />
				<span className="text-xs text-(--color-foreground-secondary)">
					{data?.activeCopilotSessions ?? "—"} 个 Copilot 会话
				</span>
				<div className="flex-1" />
				<a
					href="/ai/agents"
					className="text-xs text-(--color-accent) hover:underline"
				>
					查看全部
				</a>
			</div>
		</DittoErrorBoundary>
	);
}
