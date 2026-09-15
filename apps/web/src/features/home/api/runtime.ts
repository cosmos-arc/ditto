import { isMockRuntime } from "@/api/runtime-config";

export function shouldUseHomePrototypeMocks(): boolean {
	return isMockRuntime();
}
