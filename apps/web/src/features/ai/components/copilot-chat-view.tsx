import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useCopilotMessages } from "../hooks";

interface CopilotChatViewProps {
	readonly sessionId: string;
}

function RoleLabel({ role }: { readonly role: string }) {
	if (role === "user") {
		return <span className="text-xs font-medium text-(--color-foreground-tertiary)">你</span>;
	}
	return <span className="text-xs font-medium text-(--color-agent-thinking)">Copilot</span>;
}

function MessageBubble({ role, content }: { readonly role: string; readonly content: string }) {
	const isUser = role === "user";

	return (
		<div className="flex gap-3 py-3">
			<div className={isUser ? "ml-auto max-w-[80%]" : "mr-auto max-w-[80%]"}>
				<RoleLabel role={role} />
				<div
					className={
						isUser
							? "mt-1 whitespace-pre-line rounded-lg rounded-tr-sm bg-(--color-surface-3) px-3 py-2 text-sm text-(--color-foreground)"
							: "mt-1 whitespace-pre-line rounded-lg rounded-tl-sm bg-(--color-surface-2) px-3 py-2 text-sm text-(--color-foreground)"
					}
				>
					{content}
				</div>
			</div>
		</div>
	);
}

export function CopilotChatView({ sessionId }: CopilotChatViewProps) {
	const { data, isLoading, refetch } = useCopilotMessages(sessionId);

	if (isLoading) {
		return (
			<div className="p-4">
				<LoadingSkeleton variant="panel" rows={5} />
			</div>
		);
	}

	return (
		<DittoErrorBoundary
			fallbackProps={{
				title: "消息加载失败",
				onRetry: () => void refetch(),
			}}
		>
			<div className="flex-1 overflow-y-auto p-4">
				{data?.messages.map((message) => (
					<MessageBubble key={message.id} role={message.role} content={message.content} />
				))}
			</div>
		</DittoErrorBoundary>
	);
}
