import { isMockRuntime } from "@/api";

export function shouldUsePrototypeMocks(): boolean {
	return isMockRuntime();
}
