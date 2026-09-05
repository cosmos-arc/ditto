import type { ReactNode } from "react";
import { GlobalCommandButton } from "./global-command-button";
import { ViewPreferencesMenu } from "./view-preferences-menu";

interface HeaderUtilityBarProps {
	readonly onOpenCommand?: (() => void) | undefined;
	readonly onOpenAgent?: (() => void) | undefined;
}

function UtilityIconButton({
	"aria-label": ariaLabel,
	children,
	onClick,
	utility,
}: {
	readonly "aria-label": string;
	readonly children: ReactNode;
	readonly onClick?: (() => void) | undefined;
	readonly utility: "agent" | "notifications" | "help";
}) {
	return (
		<button
			type="button"
			aria-label={ariaLabel}
			data-shell-utility={utility}
			onClick={onClick}
			className="relative flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-foreground-tertiary)] transition-colors hover:bg-[var(--color-interaction-hover-subtle-bg)] hover:text-[var(--color-foreground-secondary)]"
		>
			{children}
		</button>
	);
}

export function HeaderUtilityBar({ onOpenAgent, onOpenCommand }: HeaderUtilityBarProps) {
	return (
		<div className="flex items-center gap-[var(--spacing-2)]" data-slot="header-utility-bar">
			<GlobalCommandButton onOpenCommand={onOpenCommand} />
			<UtilityIconButton aria-label="打开 Agent 工作入口" utility="agent" onClick={onOpenAgent}>
				<svg width={16} height={16} viewBox="0 0 20 20" fill="none" aria-hidden="true">
					<path
						d="M10 2l2.5 5.5L18 9l-4 4 1 6-5-2.5L5 19l1-6-4-4 5.5-1.5L10 2z"
						stroke="currentColor"
						strokeWidth={1.5}
						strokeLinejoin="round"
					/>
				</svg>
			</UtilityIconButton>
			<UtilityIconButton aria-label="通知" utility="notifications">
				<svg width={16} height={16} viewBox="0 0 20 20" fill="none" aria-hidden="true">
					<path
						d="M10 3a5 5 0 00-5 5v4l-2 2h14l-2-2V8a5 5 0 00-5-5z"
						stroke="currentColor"
						strokeWidth={1.5}
						strokeLinecap="round"
						strokeLinejoin="round"
					/>
					<path d="M8 16a2 2 0 004 0" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" />
				</svg>
				<span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[var(--color-red-400)]" />
			</UtilityIconButton>
			<UtilityIconButton aria-label="帮助" utility="help">
				<svg width={16} height={16} viewBox="0 0 20 20" fill="none" aria-hidden="true">
					<circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth={1.5} />
					<path
						d="M7.5 7.5a2.5 2.5 0 014.5 1.5c0 2-3 2.5-3 4m0 2h.01"
						stroke="currentColor"
						strokeWidth={1.5}
						strokeLinecap="round"
						strokeLinejoin="round"
					/>
				</svg>
			</UtilityIconButton>
			<ViewPreferencesMenu />
		</div>
	);
}
