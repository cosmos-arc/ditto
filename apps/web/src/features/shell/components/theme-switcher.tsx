import { useUIPreferences } from "../hooks/use-ui-preferences";
import type { Density, Theme } from "../hooks/use-ui-preferences";

const densityOptions: readonly { readonly value: Density; readonly label: string }[] = [
	{ value: "dense", label: "紧凑" },
	{ value: "default", label: "标准" },
	{ value: "comfortable", label: "宽松" },
];

const themeOptions: readonly { readonly value: Theme; readonly label: string }[] = [
	{ value: "light", label: "亮色" },
	{ value: "dark", label: "暗色" },
];

/**
 * ThemeSwitcher -- compact theme + density toggle in the Shell Header.
 * Renders two inline button groups: density (3-state) and theme (2-state).
 */
export function ThemeSwitcher() {
	const theme = useUIPreferences((s) => s.theme);
	const density = useUIPreferences((s) => s.density);
	const setTheme = useUIPreferences((s) => s.setTheme);
	const setDensity = useUIPreferences((s) => s.setDensity);
	const applyThemeToDom = useUIPreferences((s) => s.applyThemeToDom);

	function handleDensityChange(value: Density) {
		setDensity(value);
		applyThemeToDom();
	}

	function handleThemeChange(value: Theme) {
		setTheme(value);
		applyThemeToDom();
	}

	return (
		<div data-slot="theme-switcher" className="flex items-center gap-1">
			{/* Density group */}
			<div className="flex items-center gap-0.5 rounded-md bg-(--color-surface-panel-base) p-0.5">
				{densityOptions.map((opt) => (
					<button
						key={opt.value}
						type="button"
						aria-label={opt.label}
						data-active={density === opt.value}
						onClick={() => handleDensityChange(opt.value)}
						className={[
							"h-6 w-6 flex items-center justify-center rounded-sm text-xs transition-colors",
							density === opt.value
								? "bg-(--color-surface-2) text-(--color-foreground)"
								: "text-(--color-foreground-tertiary) hover:text-(--color-foreground-secondary)",
						].join(" ")}
					>
						{opt.value === "dense" ? "紧" : opt.value === "default" ? "标" : "松"}
					</button>
				))}
			</div>

			{/* Theme group */}
			<div className="flex items-center gap-0.5 rounded-md bg-(--color-surface-panel-base) p-0.5">
				{themeOptions.map((opt) => (
					<button
						key={opt.value}
						type="button"
						aria-label={opt.label}
						data-active={theme === opt.value}
						onClick={() => handleThemeChange(opt.value)}
						className={[
							"h-6 w-6 flex items-center justify-center rounded-sm transition-colors",
							theme === opt.value
								? "bg-(--color-surface-2) text-(--color-foreground)"
								: "text-(--color-foreground-tertiary) hover:text-(--color-foreground-secondary)",
						].join(" ")}
					>
						{opt.value === "light" ? <SunIcon /> : <MoonIcon />}
					</button>
				))}
			</div>
		</div>
	);
}

function SunIcon() {
	return (
		<svg
			width={12}
			height={12}
			viewBox="0 0 12 12"
			fill="none"
			aria-hidden="true"
		>
			<circle cx="6" cy="6" r="2.5" stroke="currentColor" strokeWidth={1.2} />
			<path
				d="M6 1v1M6 10v1M1 6h1M10 6h1M2.5 2.5l.7.7M8.8 8.8l.7.7M2.5 9.5l.7-.7M8.8 3.2l.7-.7"
				stroke="currentColor"
				strokeWidth={1.2}
				strokeLinecap="round"
			/>
		</svg>
	);
}

function MoonIcon() {
	return (
		<svg
			width={12}
			height={12}
			viewBox="0 0 12 12"
			fill="none"
			aria-hidden="true"
		>
			<path
				d="M6.5 1.5a4.5 4.5 0 1 0 4 6.5A3.5 3.5 0 0 1 6.5 1.5Z"
				stroke="currentColor"
				strokeWidth={1.2}
				strokeLinecap="round"
				strokeLinejoin="round"
			/>
		</svg>
	);
}
