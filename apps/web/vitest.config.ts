import path from "node:path";
import { defineConfig } from "vitest/config";

const coverageMode = process.argv.includes("--coverage");

export default defineConfig({
	define: {
		__DITTO_WEB_BUILD_METADATA__: JSON.stringify({
			productVersion: "0.1.0",
			gitSha: "a".repeat(40),
			apiContractVersion: "v1",
			apiContractSha256: "b".repeat(64),
			compatibilityPolicy: {
				schema: "ditto.cohort-compatibility-policy",
				schemaVersion: 1,
				policySha256: "c".repeat(64),
				current: {
					productVersion: "0.1.0",
					gitSha: "a".repeat(40),
					apiContractVersion: "v1",
					apiContractSha256: "b".repeat(64),
				},
				previous: [],
			},
		}),
	},
	resolve: {
		alias: {
			"@": path.resolve(import.meta.dirname, "./src"),
		},
	},
	test: {
		// Instrumentation makes the interaction-heavy governance suites several
		// times slower. Keep ordinary unit feedback at Vitest's strict 5s default,
		// while giving the same assertions a bounded budget under coverage.
		testTimeout: coverageMode ? 30_000 : 5_000,
		projects: [
			{
				extends: true,
				test: {
					name: "unit",
					globals: true,
					environment: "jsdom",
					retry: 0,
					setupFiles: ["./src/test/setup.ts"],
					include: ["src/**/*.test.{ts,tsx}"],
				},
			},
			{
				extends: true,
				test: {
					name: "prototype",
					globals: true,
					environment: "node",
					retry: 0,
					include: ["scripts/**/*.test.{ts,mjs}"],
				},
			},
		],
		coverage: {
			provider: "custom",
			customProviderModule: "./scripts/vitest-coverage-provider.mjs",
			include: ["src/**/*.{ts,tsx}"],
			exclude: [
				"src/**/*.test.{ts,tsx}",
				"src/**/*.d.ts",
				"src/api/generated/**",
				"src/test/**",
				"src/main.tsx",
				"src/routeTree.gen.ts",
			],
			reporter: ["text", "json"],
			thresholds: {
				statements: 82,
				branches: 80,
				functions: 82,
				lines: 85,
				"src/api/**/*.{ts,tsx}": { branches: 90 },
				"src/features/*/api.{ts,tsx}": { branches: 90 },
				"src/features/*/api/**/*.{ts,tsx}": { branches: 90 },
				"src/features/agent/api/agent-api.ts": { branches: 90 },
				"src/features/data-products/api/operations.ts": { branches: 90 },
				"src/routes/system/approvals.tsx": { branches: 90 },
				"src/features/portfolio/api/intents.ts": { branches: 90 },
				"src/features/portfolio/api/paper-accounts.ts": { branches: 90 },
				"src/features/portfolio/hooks/use-order-detail.ts": { branches: 90 },
				"src/features/portfolio/hooks/use-orders.ts": { branches: 90 },
				"src/features/portfolio/hooks/use-orders-summary.ts": { branches: 90 },
				"src/features/research/components/experiment-run-controls.tsx": { branches: 90 },
				"src/features/strategy/api/strategy-lifecycle.ts": { branches: 90 },
				"src/features/strategy/hooks/use-strategy-governance.ts": { branches: 90 },
			},
		},
	},
});
