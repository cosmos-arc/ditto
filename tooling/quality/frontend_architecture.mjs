#!/usr/bin/env bun

import { spawnSync } from "node:child_process";
import { readdir, readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

import {
	findRawColorPrimitives,
	isCanonicalTokenFile,
} from "./frontend_color_policy.mjs";

const REPOSITORY_ROOT = path.resolve(import.meta.dir, "../..");
const WEB_ROOT = path.join(REPOSITORY_ROOT, "apps/web");
const requireFromWeb = createRequire(path.join(WEB_ROOT, "package.json"));
const ts = requireFromWeb("typescript");
const SOURCE_EXTENSIONS = new Set([".css", ".js", ".jsx", ".ts", ".tsx"]);
const DIRECT_NETWORK_CAPABILITIES = new Set([
	"EventSource",
	"WebSocket",
	"XMLHttpRequest",
	"fetch",
	"sendBeacon",
]);
const API_CLIENT_FACTORIES = new Set(["createApiClient", "getApiClient"]);
const API_CLIENT_CAPABILITY_TYPES = new Set([
	"ApiClient",
	"EventStreamRequest",
]);
const API_CLIENT_METHODS = new Set([
	"delete",
	"get",
	"getEventStream",
	"getPayload",
	"patch",
	"post",
	"put",
]);

function normalizedWebPath(relativeWebPath) {
	return relativeWebPath.split(path.sep).join("/");
}

function isCoreApiPath(relativeWebPath) {
	return /^src\/api(?:\/|$)/u.test(relativeWebPath);
}

function isLegacyApiClientPath(relativeWebPath) {
	return /^src\/lib\/api-client(?:[./]|$)/u.test(relativeWebPath);
}

function isFeatureApiAdapter(relativeWebPath) {
	return /^src\/features\/[^/]+\/api(?:\/|\.(?:js|jsx|ts|tsx)$)/u.test(
		relativeWebPath,
	);
}

function isExplicitTestOrMockPath(relativeWebPath) {
	return (
		/\.(?:test|spec)\.(?:js|jsx|ts|tsx)$/u.test(relativeWebPath) ||
		/(?:^|\/)(?:__mocks__|__tests__)(?:\/|$)/u.test(relativeWebPath) ||
		/^src\/(?:mocks|test|tests)(?:\/|$)/u.test(relativeWebPath)
	);
}

function sourceModulePath(relativeWebPath, specifier) {
	const pathOnly = specifier.split(/[?#]/u, 1)[0];
	if (pathOnly.startsWith("@/"))
		return path.posix.normalize(`src/${pathOnly.slice(2)}`);
	if (pathOnly.startsWith("/src/"))
		return path.posix.normalize(pathOnly.slice(1));
	if (pathOnly.startsWith(".")) {
		return path.posix.normalize(
			path.posix.join(path.posix.dirname(relativeWebPath), pathOnly),
		);
	}
	return undefined;
}

function constantString(node) {
	if (ts.isStringLiteralLike(node)) return node.text;
	if (ts.isParenthesizedExpression(node))
		return constantString(node.expression);
	if (
		ts.isBinaryExpression(node) &&
		node.operatorToken.kind === ts.SyntaxKind.PlusToken
	) {
		const left = constantString(node.left);
		const right = constantString(node.right);
		return left === undefined || right === undefined ? undefined : left + right;
	}
	if (ts.isTemplateExpression(node)) {
		let value = node.head.text;
		for (const span of node.templateSpans) {
			const expression = constantString(span.expression);
			if (expression === undefined) return undefined;
			value += expression + span.literal.text;
		}
		return value;
	}
	return undefined;
}

function unwrappedExpression(node) {
	let current = node;
	while (
		ts.isParenthesizedExpression(current) ||
		ts.isAsExpression(current) ||
		ts.isTypeAssertionExpression(current) ||
		ts.isNonNullExpression(current) ||
		ts.isSatisfiesExpression(current)
	) {
		current = current.expression;
	}
	return current;
}

function accessedName(node) {
	const expression = unwrappedExpression(node);
	if (ts.isIdentifier(expression)) return expression.text;
	if (ts.isPropertyAccessExpression(expression)) return expression.name.text;
	if (ts.isElementAccessExpression(expression))
		return constantString(expression.argumentExpression);
	if (ts.isComputedPropertyName(expression))
		return constantString(expression.expression);
	return undefined;
}

function scriptKind(relativeWebPath) {
	switch (path.posix.extname(relativeWebPath)) {
		case ".js":
			return ts.ScriptKind.JS;
		case ".jsx":
			return ts.ScriptKind.JSX;
		case ".tsx":
			return ts.ScriptKind.TSX;
		default:
			return ts.ScriptKind.TS;
	}
}

/**
 * Find source-level escapes around the typed HTTP transport. Tests consume this
 * pure function so changes to the executable repository gate remain regression-tested.
 */
export function findNetworkBoundaryViolations(source, inputRelativeWebPath) {
	const relativeWebPath = normalizedWebPath(inputRelativeWebPath);
	const isTestOrMock = isExplicitTestOrMockPath(relativeWebPath);
	if (path.posix.extname(relativeWebPath) === ".css" || isTestOrMock) return [];
	const sourceFile = ts.createSourceFile(
		relativeWebPath,
		source,
		ts.ScriptTarget.Latest,
		true,
		scriptKind(relativeWebPath),
	);
	const isCoreApi = isCoreApiPath(relativeWebPath);
	const mayUseNetworkCapability = isCoreApi;
	const mayUseTypedClient = isCoreApi || isFeatureApiAdapter(relativeWebPath);
	const findings = [];
	const seen = new Set();

	function addFinding(rule, message, node, capability) {
		const key = `${rule}:${capability ?? ""}`;
		if (seen.has(key)) return;
		seen.add(key);
		findings.push({
			rule,
			message,
			line:
				sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile))
					.line + 1,
			...(capability === undefined ? {} : { capability }),
		});
	}

	const apiClientBindings = new Set(["apiClient"]);
	for (const statement of sourceFile.statements) {
		if (
			!ts.isImportDeclaration(statement) ||
			!ts.isStringLiteralLike(statement.moduleSpecifier)
		)
			continue;
		const moduleSpecifier = statement.moduleSpecifier.text;
		const importedPath = sourceModulePath(relativeWebPath, moduleSpecifier);
		if (importedPath && isLegacyApiClientPath(importedPath)) {
			addFinding(
				"legacy-api-client-import",
				"arbitrary legacy API client imports are forbidden",
				statement.moduleSpecifier,
			);
		}
		if (
			!mayUseNetworkCapability &&
			(moduleSpecifier === "openapi-fetch" ||
				moduleSpecifier.startsWith("openapi-fetch/"))
		) {
			addFinding(
				"raw-transport-import",
				"openapi-fetch is restricted to the src/api transport implementation",
				statement.moduleSpecifier,
			);
		}
		const bindings = statement.importClause?.namedBindings;
		if (
			bindings &&
			ts.isNamespaceImport(bindings) &&
			importedPath &&
			isCoreApiPath(importedPath) &&
			!isCoreApi
		) {
			addFinding(
				"api-client-factory-location",
				"core API namespace imports expose transport factories outside src/api",
				bindings,
				"namespace",
			);
		}
		if (!bindings || !ts.isNamedImports(bindings)) continue;
		for (const binding of bindings.elements) {
			const importedName = (binding.propertyName ?? binding.name).text;
			if (importedName === "apiClient")
				apiClientBindings.add(binding.name.text);
			if (!mayUseTypedClient && API_CLIENT_CAPABILITY_TYPES.has(importedName)) {
				addFinding(
					"typed-client-location",
					`${importedName} is restricted to feature API adapters`,
					binding,
				);
			}
			if (
				!mayUseNetworkCapability &&
				DIRECT_NETWORK_CAPABILITIES.has(importedName)
			) {
				addFinding(
					"direct-network-access",
					`${importedName} access is restricted to src/api and explicit test or mock scopes`,
					binding,
					importedName,
				);
			}
			if (!mayUseNetworkCapability && API_CLIENT_FACTORIES.has(importedName)) {
				addFinding(
					"api-client-factory-location",
					`${importedName} is restricted to src/api and explicit test or mock scopes`,
					binding,
					importedName,
				);
			}
		}
	}

	function isApiClientReference(node) {
		const expression = unwrappedExpression(node);
		if (ts.isIdentifier(expression))
			return apiClientBindings.has(expression.text);
		if (ts.isPropertyAccessExpression(expression)) {
			return expression.name.text === "apiClient";
		}
		if (ts.isElementAccessExpression(expression)) {
			return constantString(expression.argumentExpression) === "apiClient";
		}
		return false;
	}

	const variableAliases = [];
	function collectAliases(node) {
		if (
			ts.isVariableDeclaration(node) &&
			ts.isIdentifier(node.name) &&
			node.initializer
		) {
			variableAliases.push(node);
		}
		if (
			ts.isVariableDeclaration(node) &&
			ts.isObjectBindingPattern(node.name)
		) {
			for (const binding of node.name.elements) {
				if (
					ts.isIdentifier(binding.name) &&
					accessedName(binding.propertyName ?? binding.name) === "apiClient"
				) {
					apiClientBindings.add(binding.name.text);
				}
			}
		}
		ts.forEachChild(node, collectAliases);
	}
	collectAliases(sourceFile);
	let addedAlias = true;
	while (addedAlias) {
		addedAlias = false;
		for (const declaration of variableAliases) {
			if (
				apiClientBindings.has(declaration.name.text) ||
				!isApiClientReference(declaration.initializer)
			)
				continue;
			apiClientBindings.add(declaration.name.text);
			addedAlias = true;
		}
	}

	function inspect(node) {
		if (!mayUseTypedClient && isApiClientReference(node)) {
			addFinding(
				"typed-client-location",
				"typed transport clients belong in feature API adapters",
				node,
			);
		}
		if (
			ts.isCallExpression(node) &&
			node.expression.kind === ts.SyntaxKind.ImportKeyword
		) {
			const specifier = node.arguments[0]
				? constantString(node.arguments[0])
				: undefined;
			if (specifier === undefined) {
				if (!mayUseNetworkCapability) {
					addFinding(
						"opaque-dynamic-import",
						"production dynamic imports must use a statically analyzable module specifier",
						node,
					);
				}
			} else {
				if (
					!mayUseNetworkCapability &&
					(specifier === "openapi-fetch" ||
						specifier.startsWith("openapi-fetch/"))
				) {
					addFinding(
						"raw-transport-import",
						"openapi-fetch is restricted to the src/api transport implementation",
						node,
					);
				}
				const importedPath = sourceModulePath(relativeWebPath, specifier);
				if (importedPath && isLegacyApiClientPath(importedPath)) {
					addFinding(
						"legacy-api-client-import",
						"arbitrary legacy API client imports are forbidden",
						node,
					);
				}
				if (
					importedPath?.includes("api/generated/operation-contracts") &&
					!isCoreApi
				) {
					addFinding(
						"generated-runtime-contract-location",
						"generated runtime contracts are restricted to src/api",
						node,
					);
				}
				if (
					importedPath &&
					isCoreApiPath(importedPath) &&
					!mayUseNetworkCapability
				) {
					addFinding(
						"dynamic-core-api-import",
						"production code must not dynamically import the core API boundary",
						node,
					);
				}
			}
		}

		const name = accessedName(node);
		if (
			!mayUseNetworkCapability &&
			name &&
			DIRECT_NETWORK_CAPABILITIES.has(name)
		) {
			addFinding(
				"direct-network-access",
				`${name} access is restricted to src/api and explicit test or mock scopes`,
				node,
				name,
			);
		}
		if (!mayUseNetworkCapability && name && API_CLIENT_FACTORIES.has(name)) {
			addFinding(
				"api-client-factory-location",
				`${name} is restricted to src/api and explicit test or mock scopes`,
				node,
				name,
			);
		}

		if (
			ts.isPropertyAccessExpression(node) ||
			ts.isElementAccessExpression(node)
		) {
			const method = accessedName(node);
			if (
				method &&
				API_CLIENT_METHODS.has(method) &&
				isApiClientReference(node.expression)
			) {
				if (!mayUseTypedClient) {
					addFinding(
						"typed-client-location",
						"typed transport calls belong in feature API adapters",
						node,
					);
				}
				if (
					ts.isCallExpression(node.parent) &&
					node.parent.expression === node &&
					node.parent.typeArguments?.length
				) {
					addFinding(
						"caller-selected-response-type",
						"callers may not select API response types",
						node.parent,
					);
				}
			}
		}

		ts.forEachChild(node, inspect);
	}
	inspect(sourceFile);
	return findings;
}

async function sourceFiles(directory) {
	const files = [];
	for (const entry of await readdir(directory, { withFileTypes: true })) {
		const absolute = path.join(directory, entry.name);
		if (entry.isDirectory()) files.push(...(await sourceFiles(absolute)));
		else if (entry.isFile() && SOURCE_EXTENSIONS.has(path.extname(entry.name)))
			files.push(absolute);
	}
	return files;
}

async function main() {
	const errors = [];
	for (const relativeDirectory of ["src/components/ui", "src/lib"]) {
		for (const file of await sourceFiles(
			path.join(WEB_ROOT, relativeDirectory),
		)) {
			const text = await readFile(file, "utf8");
			if (
				/from\s+["']@\/features\//u.test(text) ||
				/from\s+["'](?:\.\.\/)+features\//u.test(text)
			) {
				errors.push(
					`${path.relative(REPOSITORY_ROOT, file)}: low-level code must not import feature internals`,
				);
			}
		}
	}

	for (const file of await sourceFiles(path.join(WEB_ROOT, "src"))) {
		const text = await readFile(file, "utf8");
		const relativeWebPath = normalizedWebPath(path.relative(WEB_ROOT, file));
		const mayImportGeneratedSchema =
			relativeWebPath.startsWith("src/api/") ||
			/^src\/features\/[^/]+\/api(?:\/|\.ts$)/u.test(relativeWebPath);
		if (
			!mayImportGeneratedSchema &&
			/(?:from\s+|import\s*)["'][^"']*api\/generated\/schema["']/u.test(text)
		) {
			errors.push(
				`${path.relative(REPOSITORY_ROOT, file)}: generated schema imports are restricted to src/api and feature API adapters`,
			);
		}
		if (
			!relativeWebPath.startsWith("src/api/") &&
			/(?:from\s+|import\s*)["'][^"']*api\/generated\/operation-contracts["']/u.test(
				text,
			)
		) {
			errors.push(
				`${path.relative(REPOSITORY_ROOT, file)}: generated runtime contracts are restricted to src/api`,
			);
		}
		if (/\bVITE_API_BASE_URL\b/u.test(text)) {
			errors.push(
				`${path.relative(REPOSITORY_ROOT, file)}: production API routing must come from runtime config`,
			);
		}
		for (const finding of findNetworkBoundaryViolations(
			text,
			relativeWebPath,
		)) {
			errors.push(
				`${path.relative(REPOSITORY_ROOT, file)}:${finding.line}: ${finding.message}`,
			);
		}
		if (/\.(?:test|spec)\.(?:js|jsx|ts|tsx)$/u.test(file)) continue;
		if (/@ts-ignore|@ts-expect-error/u.test(text))
			errors.push(
				`${path.relative(REPOSITORY_ROOT, file)}: TypeScript suppression is forbidden`,
			);
		if (!isCanonicalTokenFile(relativeWebPath)) {
			for (const finding of findRawColorPrimitives(text, relativeWebPath)) {
				errors.push(
					`${path.relative(REPOSITORY_ROOT, file)}:${finding.line}: raw ${finding.syntax} color must be defined in src/styles/design-tokens`,
				);
			}
		}
	}

	const dependencyCruiser = path.join(WEB_ROOT, "node_modules/.bin/depcruise");
	const typescriptLoader = path.join(
		WEB_ROOT,
		"scripts/dependency-cruiser-typescript-loader.mjs",
	);
	const cruise = spawnSync(
		dependencyCruiser,
		[
			"--config",
			"dependency-cruiser.config.mjs",
			"--output-type",
			"json",
			"src",
		],
		{
			cwd: WEB_ROOT,
			encoding: "utf8",
			env: {
				...process.env,
				NODE_OPTIONS: [process.env.NODE_OPTIONS, `--import=${typescriptLoader}`]
					.filter(Boolean)
					.join(" "),
				NODE_PATH: [path.join(WEB_ROOT, "node_modules"), process.env.NODE_PATH]
					.filter(Boolean)
					.join(path.delimiter),
			},
			maxBuffer: 16 * 1024 * 1024,
		},
	);
	if (cruise.error) {
		errors.push(`dependency-cruiser failed to start: ${cruise.error.message}`);
	} else {
		let cruiseResult;
		try {
			cruiseResult = JSON.parse(cruise.stdout);
		} catch {
			const output = `${cruise.stdout ?? ""}${cruise.stderr ?? ""}`.trim();
			errors.push(
				output ||
					`dependency-cruiser exited with status ${cruise.status ?? "unknown"}`,
			);
		}

		if (cruiseResult) {
			const totalCruised = cruiseResult.summary?.totalCruised ?? 0;
			if (totalCruised === 0) {
				errors.push("dependency-cruiser did not analyze any source modules");
			}
			const typescript =
				cruiseResult.summary?.environment?.transpilersFound?.find(
					(transpiler) => transpiler.name === "typescript",
				);
			if (!typescript?.available) {
				errors.push("dependency-cruiser did not load the TypeScript parser");
			}

			for (const violation of cruiseResult.summary?.violations ?? []) {
				if (violation.rule?.severity !== "error") continue;
				errors.push(
					`${violation.rule.name}: ${violation.from} -> ${violation.to}`,
				);
			}

			const featureGraph = new Map();
			const testModule = /\.(?:test|spec)\.(?:js|jsx|ts|tsx)$/u;
			const featureName = (modulePath) =>
				/^src\/features\/([^/]+)\//u.exec(modulePath)?.[1];
			for (const module of cruiseResult.modules ?? []) {
				if (testModule.test(module.source)) continue;
				const fromFeature = featureName(module.source);
				if (!fromFeature) continue;
				if (!featureGraph.has(fromFeature))
					featureGraph.set(fromFeature, new Set());
				for (const dependency of module.dependencies ?? []) {
					if (testModule.test(dependency.resolved)) continue;
					const toFeature = featureName(dependency.resolved);
					if (toFeature && toFeature !== fromFeature)
						featureGraph.get(fromFeature).add(toFeature);
				}
			}

			let nextIndex = 0;
			const indices = new Map();
			const lowLinks = new Map();
			const stack = [];
			const onStack = new Set();
			const stronglyConnected = [];
			function visit(feature) {
				indices.set(feature, nextIndex);
				lowLinks.set(feature, nextIndex);
				nextIndex += 1;
				stack.push(feature);
				onStack.add(feature);

				for (const dependency of featureGraph.get(feature) ?? []) {
					if (!indices.has(dependency)) {
						visit(dependency);
						lowLinks.set(
							feature,
							Math.min(lowLinks.get(feature), lowLinks.get(dependency)),
						);
					} else if (onStack.has(dependency)) {
						lowLinks.set(
							feature,
							Math.min(lowLinks.get(feature), indices.get(dependency)),
						);
					}
				}

				if (lowLinks.get(feature) !== indices.get(feature)) return;
				const component = [];
				let member;
				do {
					member = stack.pop();
					onStack.delete(member);
					component.push(member);
				} while (member !== feature);
				if (component.length > 1) stronglyConnected.push(component.sort());
			}

			for (const feature of featureGraph.keys()) {
				if (!indices.has(feature)) visit(feature);
			}
			for (const cycle of stronglyConnected.sort((left, right) =>
				left[0].localeCompare(right[0]),
			)) {
				errors.push(`feature-dependency-cycle: ${cycle.join(" <-> ")}`);
			}
		}
	}

	if (errors.length > 0) {
		process.stderr.write(`${errors.join("\n")}\n`);
		process.exit(1);
	}
	process.stdout.write("Frontend architecture checks passed.\n");
}

if (import.meta.main) await main();
