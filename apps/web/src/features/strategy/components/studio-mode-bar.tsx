import { useState } from "react";

interface StudioMode {
	id: string;
	label: string;
}

interface StudioModeBarProps {
	/** Available modes */
	modes: readonly StudioMode[];
	/** Currently active mode id */
	activeMode?: string;
	/** Breadcrumb segments (last segment is the current item) */
	breadcrumbs?: readonly string[];
	/** Callback when mode changes */
	onModeChange?: (modeId: string) => void;
}

/**
 * StudioModeBar — Mode/tab switching bar for StudioLayout.
 * Matches prototype .studio-mode-bar: mode-tabs + separator + breadcrumb.
 */
export function StudioModeBar({
	modes,
	activeMode,
	breadcrumbs,
	onModeChange,
}: StudioModeBarProps) {
	const [internalActive, setInternalActive] = useState(modes[0]?.id ?? "");
	const currentMode = activeMode ?? internalActive;

	return (
		<div
			className="flex h-[var(--density-strip-height)] shrink-0 items-center gap-4 border-b border-b-(--color-border-subtle) bg-(--color-surface-1) px-(--density-panel-padding)"
			data-slot="studio-mode-bar"
			role="tablist"
			aria-label="编辑模式"
		>
			<div className="flex items-center">
				{modes.map((mode) => (
					<button
						key={mode.id}
						type="button"
						role="tab"
						aria-selected={currentMode === mode.id}
						tabIndex={currentMode === mode.id ? 0 : -1}
						onClick={() => {
							if (onModeChange) {
								onModeChange(mode.id);
							} else {
								setInternalActive(mode.id);
							}
						}}
						className={[
							"cursor-pointer border-b-2 px-3 py-1 text-xs font-medium transition-colors",
							"flex items-center gap-1.5",
							currentMode === mode.id
								? "border-b-(--color-accent) text-(--color-foreground)"
								: "border-b-transparent text-(--color-foreground-tertiary) hover:bg-(--color-interaction-hover-subtle-bg) hover:text-(--color-foreground-secondary)",
						].join(" ")}
					>
						{mode.label}
					</button>
				))}
			</div>

			{breadcrumbs && breadcrumbs.length > 0 && (
				<>
					<div className="h-3.5 w-px bg-(--color-border-subtle)" />
					<nav className="flex items-center gap-1 text-xs text-(--color-foreground-tertiary)">
						{breadcrumbs.map((crumb, i) => {
							const isLast = i === breadcrumbs.length - 1;
							return (
								<span key={crumb} className="flex items-center gap-1">
									{i > 0 && <span aria-hidden="true">/</span>}
									<span className={isLast ? "text-(--color-foreground-secondary)" : ""}>
										{crumb}
									</span>
								</span>
							);
						})}
					</nav>
				</>
			)}
		</div>
	);
}
