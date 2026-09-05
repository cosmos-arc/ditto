import type { ReactNode } from "react";
import { useState } from "react";
import { AgentContextActions, AgentLauncherSidecar } from "@/features/agent";
import { WorkspaceShell } from "@/features/shell";
import { ContextActionsProvider, type ContextActionsRequest } from "@/providers";

interface AppShellProps {
	readonly children: ReactNode;
}

function renderAgentContextActions(request: ContextActionsRequest): ReactNode {
	return <AgentContextActions {...request} />;
}

export function AppShell({ children }: AppShellProps) {
	const [isAgentLauncherOpen, setIsAgentLauncherOpen] = useState(false);

	return (
		<ContextActionsProvider renderActions={renderAgentContextActions}>
			<WorkspaceShell
				onOpenLauncher={() => setIsAgentLauncherOpen(true)}
				launcher={(activeDomain) => (
					<AgentLauncherSidecar
						domain={activeDomain}
						open={isAgentLauncherOpen}
						onOpenChange={setIsAgentLauncherOpen}
					/>
				)}
			>
				{children}
			</WorkspaceShell>
		</ContextActionsProvider>
	);
}
