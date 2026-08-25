import { Button } from "@/components/ui/button";

function agentHref(contextType: string, contextId: string, objective: string): string {
	const search = new URLSearchParams({
		tab: "runs",
		contextType,
		contextId,
		objective,
	});
	return `/platform/agents?${search.toString()}`;
}

export function AgentContextActions({
	authorObjective,
	contextId,
	contextType,
	evidenceObjective,
	className,
}: {
	readonly authorObjective?: string;
	readonly className?: string;
	readonly contextId: string;
	readonly contextType: string;
	readonly evidenceObjective: string;
}) {
	return (
		<div
			className={className ?? "flex flex-wrap items-center gap-2"}
			data-agent-context={`${contextType}:${contextId}`}
		>
			<Button asChild size="sm" variant="outline">
				<a href={agentHref(contextType, contextId, evidenceObjective)}>请求证据分析</a>
			</Button>
			{authorObjective && (
				<Button asChild size="sm" variant="outline">
					<a href={agentHref(contextType, contextId, authorObjective)}>请求 Author 草案</a>
				</Button>
			)}
		</div>
	);
}
