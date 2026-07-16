import { useEffect } from "react";
import { CopilotChatView, CopilotContextPanel, CopilotSessionList } from "@/features/ai";

interface CopilotSidecarProps {
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
}

export function CopilotSidecar({ open, onOpenChange }: CopilotSidecarProps) {
	useEffect(() => {
		if (!open) return;

		function handleKeyDown(event: KeyboardEvent) {
			if (event.key === "Escape") {
				onOpenChange(false);
			}
		}

		document.addEventListener("keydown", handleKeyDown);
		return () => document.removeEventListener("keydown", handleKeyDown);
	}, [onOpenChange, open]);

	if (!open) {
		return null;
	}

	return (
		<aside
			role="dialog"
			aria-modal="false"
			aria-label="Copilot"
			data-slot="copilot-sidecar"
			className={[
				"fixed right-0 top-0 z-40 grid h-screen w-(--width-drawer) max-w-[calc(100vw-var(--width-rail))]",
				"grid-rows-[auto_1fr] border-l border-(--color-border-subtle)",
				"bg-(--color-surface-panel-base) shadow-[0_0_32px_color-mix(in_oklch,var(--color-accent)_10%,transparent)]",
			].join(" ")}
		>
			<header className="flex h-(--height-header) items-center justify-between border-b border-(--color-border-subtle) px-(--spacing-4)">
				<div className="min-w-0">
					<h2 className="text-sm font-semibold text-(--color-foreground)">Copilot</h2>
					<p className="text-xs text-(--color-foreground-tertiary)">全局研究与执行上下文</p>
				</div>
				<button
					type="button"
					aria-label="关闭 Copilot"
					onClick={() => onOpenChange(false)}
					className="flex h-8 w-8 items-center justify-center rounded-(--radius-md) text-(--color-foreground-tertiary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
				>
					<svg width={16} height={16} viewBox="0 0 20 20" fill="none" aria-hidden="true">
						<path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" />
					</svg>
				</button>
			</header>
			<div className="grid min-h-0 grid-cols-[minmax(10rem,14rem)_1fr] grid-rows-[1fr_auto]">
				<div className="min-h-0 border-r border-(--color-border-subtle)" data-slot="source">
					<CopilotSessionList />
				</div>
				<div className="min-h-0" data-slot="main">
					<CopilotChatView sessionId="session-001" />
				</div>
				<div className="col-span-2 min-h-0 border-t border-(--color-border-subtle)" data-slot="inspector">
					<CopilotContextPanel />
				</div>
			</div>
		</aside>
	);
}
