import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "./src"),
		},
	},
	test: {
		globals: true,
		environment: "jsdom",
		// scripts/ 下的 prototype 契约测试用 playwright 渲染原型 HTML，在全量并行下
		// 偶发尺寸/可见性测量抖动（domcontentloaded + 资源竞争导致的 flaky）。retry 吸收
		// 抖动：稳定的单元测试一次通过不触发重试，仅 flaky case 自动重跑。治本的等待策略
		// 改进（waitUntil load + fonts.ready）可作为独立后续优化。
		retry: 2,
		setupFiles: ["./src/test/setup.ts"],
		include: ["src/**/*.test.{ts,tsx}", "scripts/**/*.test.{ts,mjs}", ".agents/skills/**/*.test.mjs"],
		coverage: {
			provider: "v8",
			include: ["src/**/*.{ts,tsx}"],
			exclude: ["src/**/*.test.{ts,tsx}", "src/**/*.d.ts", "src/test/**", "src/main.tsx"],
			thresholds: {
				statements: 80,
				branches: 75,
				functions: 80,
				lines: 80,
			},
		},
	},
});
