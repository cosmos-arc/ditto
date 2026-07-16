import { AgentInspectorPanel as AiAgentInspectorPanel } from "@/features/ai";

interface AgentInspectorPanelProps {
	readonly planId?: string;
}

export function AgentInspectorPanel({ planId }: AgentInspectorPanelProps) {
	return <AiAgentInspectorPanel planId={planId} />;
}
