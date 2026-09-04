export function shouldUseHomePrototypeMocks(): boolean {
	return import.meta.env.VITE_USE_MOCK === "true";
}
