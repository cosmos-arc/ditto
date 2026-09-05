import { createContext, type ReactNode, useContext } from "react";

export interface ContextActionsRequest {
	readonly authorObjective?: string;
	readonly className?: string;
	readonly contextId: string;
	readonly contextType: string;
	readonly evidenceLabel?: string;
	readonly evidenceObjective: string;
}

export type ContextActionsRenderer = (request: ContextActionsRequest) => ReactNode;

const ContextActionsRendererContext = createContext<ContextActionsRenderer | null>(null);

export function ContextActionsProvider({
	children,
	renderActions,
}: {
	readonly children: ReactNode;
	readonly renderActions: ContextActionsRenderer;
}) {
	return (
		<ContextActionsRendererContext.Provider value={renderActions}>{children}</ContextActionsRendererContext.Provider>
	);
}

export function ContextActions(request: ContextActionsRequest) {
	const renderActions = useContext(ContextActionsRendererContext);
	return renderActions?.(request) ?? null;
}
