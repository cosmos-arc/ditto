import { useCallback, useEffect, useState } from "react";

type Theme = "dark" | "light";

const STORAGE_KEY = "ditto-theme";

function getInitialTheme(): Theme {
	const stored = localStorage.getItem(STORAGE_KEY);
	if (stored === "light" || stored === "dark") return stored;
	return "dark";
}

export function useTheme() {
	const [theme, setThemeState] = useState<Theme>(getInitialTheme);

	const applyTheme = useCallback((t: Theme) => {
		document.documentElement.classList.remove("dark", "light");
		document.documentElement.classList.add(t);
		localStorage.setItem(STORAGE_KEY, t);
	}, []);

	const setTheme = useCallback(
		(t: Theme) => {
			setThemeState(t);
			applyTheme(t);
		},
		[applyTheme],
	);

	const toggleTheme = useCallback(() => {
		setTheme(theme === "dark" ? "light" : "dark");
	}, [theme, setTheme]);

	useEffect(() => {
		applyTheme(theme);
	}, [theme, applyTheme]);

	return { theme, setTheme, toggleTheme } as const;
}
