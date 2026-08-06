/**
 * Strategy feature 运行时双轨开关。
 *
 * 与 trading feature 同构：开关按 feature 存放，hook 读取决定走 live 端点还是
 * prototype mock（MSW）。`VITE_USE_MOCK === "true"` 时测试/原型态启用 MSW handler。
 */
export function shouldUsePrototypeMocks(): boolean {
	return import.meta.env.VITE_USE_MOCK === "true";
}
