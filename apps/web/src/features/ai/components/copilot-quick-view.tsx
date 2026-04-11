import { useCopilotQuickView } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

const MODE_VARIANT_MAP: Record<string, "research" | "trade" | "platform"> = {
	research: "research",
	trading: "trade",
	coding: "platform",
	general: "platform",
};

const MODE_LABEL_MAP: Record<string, string> = {
	research: "研究",
	trading: "交易",
	coding: "编码",
	general: "通用",
};

export function CopilotQuickView() {
	const {
		data,
		isLoading,
		isError,
		refetch,
	} = useCopilotQuickView();

	return (
		<div className="grid grid-cols-2 gap-4">
			<ContextSection title="Copilot 会话" count={data?.sessions.length}>
				{isLoading && <LoadingSkeleton variant="table" rows={3} />}
				<DittoErrorBoundary
					fallbackProps={{
						title: "Copilot 会话加载失败",
						onRetry: () => void refetch(),
					}}
				>
					{data && (
						<div className="space-y-1">
							{data.sessions.map((session) => (
								<div
									key={session.id}
									className="rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<div className="flex items-center justify-between">
										<span className="text-(--color-foreground)">
											{session.title}
										</span>
										<StatusBadge
											variant={MODE_VARIANT_MAP[session.mode] ?? "platform"}
											label={MODE_LABEL_MAP[session.mode] ?? session.mode}
											size="sm"
										/>
									</div>
									<div className="mt-1 text-xs text-(--color-foreground-tertiary)">
										{session.messageCount} 条消息
									</div>
								</div>
							))}
						</div>
					)}
				</DittoErrorBoundary>
			</ContextSection>

			<ContextSection
				title="近期输出"
				count={data?.recentOutputs.length}
			>
				{isLoading && <LoadingSkeleton variant="table" rows={3} />}
				{data && (
					<div className="space-y-1">
						{data.recentOutputs.map((output) => (
							<div
								key={output.id}
								className="rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<p className="text-(--color-foreground)">
									{output.summary}
								</p>
								<div className="mt-1 text-xs text-(--color-foreground-tertiary)">
									{output.type}
								</div>
							</div>
						))}
					</div>
				)}
			</ContextSection>
		</div>
	);
}
