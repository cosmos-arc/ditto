import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { DOMAINS, type DomainId } from "@/features/navigation";

interface AgentLauncherSidecarProps {
	readonly domain: DomainId;
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
}

export function AgentLauncherSidecar({ domain, open, onOpenChange }: AgentLauncherSidecarProps) {
	const returnFocusRef = useRef<HTMLElement | null>(null);
	const domainLabel = DOMAINS.find((candidate) => candidate.id === domain)?.label ?? "Today";

	useEffect(() => {
		if (!open) return;
		returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;

		function handleKeyDown(event: KeyboardEvent) {
			if (event.key === "Escape") onOpenChange(false);
		}

		document.addEventListener("keydown", handleKeyDown);
		return () => {
			document.removeEventListener("keydown", handleKeyDown);
			returnFocusRef.current?.focus();
		};
	}, [onOpenChange, open]);

	if (!open) return null;

	return (
		<aside
			role="dialog"
			aria-modal="false"
			aria-label="Agent 工作入口"
			data-slot="agent-launcher-sidecar"
			data-agent-context-domain={domain}
			className="fixed top-0 right-0 z-40 grid h-screen w-(--width-drawer) max-w-[calc(100vw-var(--width-rail))] grid-rows-[auto_1fr] border-l border-(--color-border-subtle) bg-(--color-surface-panel-base) shadow-[0_0_32px_color-mix(in_oklch,var(--color-accent)_10%,transparent)]"
		>
			<header className="flex h-(--height-header) items-center justify-between border-b border-(--color-border-subtle) px-(--spacing-4)">
				<div className="min-w-0">
					<h2 className="text-sm font-semibold text-(--color-foreground)">Agent 工作入口</h2>
					<p className="text-xs text-(--color-foreground-tertiary)">Evidence · Author · Campaign · Approval</p>
				</div>
				<button
					type="button"
					aria-label="关闭 Agent 工作入口"
					onClick={() => onOpenChange(false)}
					className="flex h-8 w-8 items-center justify-center rounded-(--radius-md) text-(--color-foreground-tertiary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) focus-visible:ring-3 focus-visible:ring-(--color-focus-ring) focus-visible:outline-none"
				>
					<svg width={16} height={16} viewBox="0 0 20 20" fill="none" aria-hidden="true">
						<path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" />
					</svg>
				</button>
			</header>
			<div className="flex min-h-0 flex-col gap-5 overflow-y-auto p-(--spacing-4)">
				<p className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2 text-xs font-medium text-(--color-foreground-secondary)">
					当前上下文 · {domainLabel}
				</p>
				<section className="border-b border-(--color-border-subtle) pb-4">
					<p className="text-xs font-medium text-(--color-foreground)">受治理研究入口</p>
					<p className="mt-2 text-xs leading-relaxed text-(--color-foreground-secondary)">
						Agent 不再以全局聊天会话工作。请从具体策略、实验、因子或 Daily Decision 发起分析，使稳定 identity 与
						objective 一起进入 authority。
					</p>
				</section>
				<section className="space-y-3">
					<div>
						<p className="text-xs font-medium text-(--color-foreground)">历史与监督</p>
						<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
							恢复 Run/Campaign、审查 Evidence Spine 与处理 exact approval。
						</p>
					</div>
					<Button asChild className="w-full">
						<a href="/research/agent?tab=runs">进入 Research Agent Lab</a>
					</Button>
					<div className="grid grid-cols-2 gap-2">
						<Button asChild variant="outline" size="sm">
							<a href="/system/agent?tab=runs">System Agent Ops</a>
						</Button>
						<Button asChild variant="outline" size="sm">
							<a href="/system/approvals?tab=approvals">Approval Inbox</a>
						</Button>
					</div>
				</section>
				<p
					role="note"
					className="mt-auto rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) p-3 text-xs text-(--color-foreground-tertiary)"
				>
					Provider key、base URL 与 model ID 仅由服务端配置；浏览器不保存这些字段。
				</p>
			</div>
		</aside>
	);
}
