import { isMockRuntime } from "@/api/runtime-config";

export function shouldUsePrototypeMocks(): boolean {
	return isMockRuntime();
}
