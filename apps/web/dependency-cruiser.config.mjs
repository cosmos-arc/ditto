import { readdirSync } from "node:fs";

const testModule = "\\.(?:test|spec)\\.(?:js|jsx|ts|tsx)$";
const featureBarrel = "^src/features/[^/]+/index\\.(?:ts|tsx)$";
const workflowBarrels = ["^src/workflows/index\\.(?:ts|tsx)$", "^src/workflows/[^/]+/index\\.(?:ts|tsx)$"];
const foundationalFeatures = ["navigation", "shell"];

// Peer capability edges that predate workflow isolation. Listing them explicitly makes
// business feature-to-feature dependencies fail closed: a new edge is rejected until it
// is either moved into a workflow or deliberately reviewed here.
const approvedPeerFeatureDependencies = {
	agent: [],
	backtest: [],
	"data-products": [],
	home: ["agent", "markets", "portfolio"],
	instruments: [],
	markets: [],
	portfolio: [],
	research: [],
	selection: [],
	strategy: [],
	system: [],
};

const businessFeatures = readdirSync(new URL("./src/features/", import.meta.url), { withFileTypes: true })
	.filter((entry) => entry.isDirectory() && !foundationalFeatures.includes(entry.name))
	.map((entry) => entry.name)
	.sort();
const registeredBusinessFeatures = Object.keys(approvedPeerFeatureDependencies).sort();
const missingRegistrations = businessFeatures.filter((feature) => !registeredBusinessFeatures.includes(feature));
const staleRegistrations = registeredBusinessFeatures.filter((feature) => !businessFeatures.includes(feature));
if (missingRegistrations.length > 0 || staleRegistrations.length > 0) {
	throw new Error(
		`Feature dependency registry drift: missing=${missingRegistrations.join(",") || "none"}; stale=${staleRegistrations.join(",") || "none"}`,
	);
}

const businessFeatureIsolationRules = Object.entries(approvedPeerFeatureDependencies).map(
	([feature, approvedPeers]) => ({
		name: `${feature}-uses-only-approved-features`,
		comment: "Business features may consume foundations and explicitly reviewed peer capabilities only.",
		severity: "error",
		from: { path: `^src/features/${feature}/`, pathNot: testModule },
		to: {
			path: `^src/features/(?!${feature}/)[^/]+/`,
			pathNot: `^src/features/(?:${[...foundationalFeatures, ...approvedPeers].join("|")})/`,
		},
	}),
);

export default {
	forbidden: [
		{
			name: "no-circular-production-dependencies",
			comment: "Production modules must form an acyclic dependency graph.",
			severity: "error",
			from: { path: "^src/", pathNot: testModule },
			to: { circular: true },
		},
		{
			name: "foundational-features-do-not-depend-on-business-features",
			comment: "Shell and navigation are foundations and may not acquire product capability dependencies.",
			severity: "error",
			from: { path: `^src/features/(?:${foundationalFeatures.join("|")})/`, pathNot: testModule },
			to: { path: `^src/features/(?!(?:${foundationalFeatures.join("|")})/)[^/]+/` },
		},
		...businessFeatureIsolationRules,
		{
			name: "cross-feature-imports-use-public-api",
			comment: "A feature may consume another feature only through its index barrel.",
			severity: "error",
			from: { path: "^src/features/([^/]+)/", pathNot: testModule },
			to: {
				path: "^src/features/(?!$1/)[^/]+/",
				pathNot: featureBarrel,
			},
		},
		{
			name: "routes-use-feature-public-api",
			comment: "Routes are composition roots and may not couple to feature internals.",
			severity: "error",
			from: { path: "^src/routes/", pathNot: testModule },
			to: { path: "^src/features/[^/]+/", pathNot: featureBarrel },
		},
		{
			name: "routes-use-workflow-public-api",
			comment: "Routes consume workflow entry points, not workflow internals.",
			severity: "error",
			from: { path: "^src/routes/", pathNot: testModule },
			to: { path: "^src/workflows/", pathNot: workflowBarrels },
		},
		{
			name: "workflows-use-feature-public-api",
			comment: "Cross-feature workflows compose stable feature APIs only.",
			severity: "error",
			from: { path: "^src/workflows/", pathNot: testModule },
			to: { path: "^src/features/[^/]+/", pathNot: featureBarrel },
		},
		{
			name: "shared-code-does-not-depend-on-features",
			comment: "Shared foundations must not acquire an inward dependency on product features.",
			severity: "error",
			from: {
				path: "^src/(?:api|components|hooks|lib|providers|stores|styles|types)/",
				pathNot: testModule,
			},
			to: { path: "^src/features/" },
		},
		{
			name: "features-do-not-depend-on-composition-roots",
			comment: "Features must stay reusable below routes and cross-feature workflows.",
			severity: "error",
			from: { path: "^src/features/", pathNot: testModule },
			to: { path: "^src/(?:routes|workflows)/" },
		},
	],
	options: {
		doNotFollow: { path: "node_modules" },
		enhancedResolveOptions: {
			exportsFields: ["exports"],
			extensions: [".js", ".jsx", ".ts", ".tsx", ".d.ts"],
			mainFields: ["module", "main", "types", "typings"],
		},
		includeOnly: "^src/",
		moduleSystems: ["es6", "cjs"],
		tsConfig: { fileName: "tsconfig.browser.json" },
		tsPreCompilationDeps: true,
	},
};
