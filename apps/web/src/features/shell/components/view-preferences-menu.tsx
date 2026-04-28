import { useState } from "react";
import { useUIPreferences } from "../hooks/use-ui-preferences";
import type { Density, Theme } from "../hooks/use-ui-preferences";

const densityOptions: readonly { readonly value: Density; readonly label: string }[] = [
	{ value: "dense", label: "紧凑" },
	{ value: "default", label: "标准" },
	{ value: "comfortable", label: "宽松" },
];

const themeOptions: readonly { readonly value: Theme; readonly label: string }[] = [
	{ value: "dark", label: "暗色" },
	{ value: "light", label: "亮色" },
];

export function ViewPreferencesMenu() {
	const [open, setOpen] = useState(false);
	const theme = useUIPreferences((state) => state.theme);
	const density = useUIPreferences((state) => state.density);
	const setTheme = useUIPreferences((state) => state.setTheme);
	const setDensity = useUIPreferences((state) => state.setDensity);

	return (
		<div className="relative" data-slot="view-preferences">
			<button
				type="button"
				aria-expanded={open}
				aria-haspopup="menu"
				aria-label="账户与视图偏好"
				data-shell-utility="account"
				onClick={() => setOpen((current) => !current)}
				className="flex h-7 w-7 items-center justify-center rounded-full bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)] text-sm font-medium text-(--color-accent) transition-colors hover:bg-[color-mix(in_oklch,var(--color-accent)_16%,transparent)]"
			>
				C
			</button>
			{open && (
				<div
					role="menu"
					aria-label="账户与视图偏好"
					data-view-preferences-menu=""
					className="absolute right-0 top-[calc(100%+var(--spacing-2))] z-20 min-w-44 rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-overlay)] p-[var(--spacing-2)] shadow-(--shadow-dragging)"
				>
					<div className="space-y-1">
						<p className="px-1 text-xs font-medium uppercase text-(--color-foreground-tertiary)">
							密度
						</p>
						<div className="grid grid-cols-3 gap-1">
							{densityOptions.map((option) => (
								<button
									key={option.value}
									type="button"
									role="menuitemradio"
									aria-checked={density === option.value}
									onClick={() => setDensity(option.value)}
									className={[
										"h-7 rounded-[var(--radius-sm)] px-2 text-xs transition-colors",
										density === option.value
											? "bg-(--color-surface-panel-elevated) text-(--color-foreground)"
											: "text-(--color-foreground-tertiary) hover:bg-(--color-interaction-hover-subtle-bg) hover:text-(--color-foreground-secondary)",
									].join(" ")}
								>
									{option.label}
								</button>
							))}
						</div>
					</div>
					<div className="mt-2 space-y-1 border-t border-(--color-border-subtle) pt-2">
						<p className="px-1 text-xs font-medium uppercase text-(--color-foreground-tertiary)">
							主题
						</p>
						<div className="grid grid-cols-2 gap-1">
							{themeOptions.map((option) => (
								<button
									key={option.value}
									type="button"
									role="menuitemradio"
									aria-checked={theme === option.value}
									onClick={() => setTheme(option.value)}
									className={[
										"h-7 rounded-[var(--radius-sm)] px-2 text-xs transition-colors",
										theme === option.value
											? "bg-(--color-surface-panel-elevated) text-(--color-foreground)"
											: "text-(--color-foreground-tertiary) hover:bg-(--color-interaction-hover-subtle-bg) hover:text-(--color-foreground-secondary)",
									].join(" ")}
								>
									{option.label}
								</button>
							))}
						</div>
					</div>
				</div>
			)}
		</div>
	);
}
