import { isMockRuntime } from "@/api";

export function shouldUseHomePrototypeMocks(): boolean {
	return isMockRuntime();
}
