import { dirname, relative, resolve } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const webRoot = resolve(import.meta.dirname, "..");
const workspaceRoot = resolve(webRoot, "../..");
const solutionConfigPath = resolve(webRoot, "tsconfig.json");
const baseConfigPath = resolve(webRoot, "tsconfig.base.json");

function formatDiagnostics(diagnostics: readonly ts.Diagnostic[]): string {
	return ts.formatDiagnosticsWithColorAndContext(diagnostics, {
		getCanonicalFileName: (fileName) => fileName,
		getCurrentDirectory: () => workspaceRoot,
		getNewLine: () => "\n",
	});
}

function readConfig(configPath: string): Record<string, unknown> {
	const result = ts.readConfigFile(configPath, ts.sys.readFile);
	if (result.error) {
		throw new Error(formatDiagnostics([result.error]));
	}
	return result.config as Record<string, unknown>;
}

function resolveReferencedConfig(referencePath: string): string {
	const candidate = resolve(dirname(solutionConfigPath), referencePath);
	return ts.sys.fileExists(candidate)
		? candidate
		: resolve(candidate, "tsconfig.json");
}

function referencedProjectFiles(): ReadonlySet<string> {
	const solution = readConfig(solutionConfigPath);
	const references = solution["references"];
	if (!Array.isArray(references)) {
		throw new Error("apps/web/tsconfig.json must declare project references");
	}

	const files = new Set<string>();
	for (const reference of references) {
		if (
			typeof reference !== "object" ||
			reference === null ||
			!("path" in reference) ||
			typeof reference.path !== "string"
		) {
			throw new Error("every TypeScript project reference must declare a path");
		}
		const configPath = resolveReferencedConfig(reference.path);
		const parsed = ts.parseJsonConfigFileContent(
			readConfig(configPath),
			ts.sys,
			dirname(configPath),
			undefined,
			configPath,
		);
		if (parsed.errors.length > 0) {
			throw new Error(formatDiagnostics(parsed.errors));
		}
		for (const fileName of parsed.fileNames) files.add(resolve(fileName));
	}
	return files;
}

describe("TypeScript project coverage", () => {
	it("keeps strict indexed and optional property checks enabled", () => {
		const compilerOptions = readConfig(baseConfigPath)["compilerOptions"];

		expect(compilerOptions).toMatchObject({
			exactOptionalPropertyTypes: true,
			noPropertyAccessFromIndexSignature: true,
			noUncheckedIndexedAccess: true,
			strict: true,
		});
	});

	it("includes every cross-stack system TypeScript file", () => {
		const systemRoot = resolve(workspaceRoot, "tests/system");
		const systemFiles = ts.sys
			.readDirectory(systemRoot, [".ts"], undefined, ["**/*.ts"])
			.map((fileName) => resolve(fileName));
		expect(systemFiles.length).toBeGreaterThan(0);

		const projectFiles = referencedProjectFiles();
		const uncovered = systemFiles
			.filter((fileName) => !projectFiles.has(fileName))
			.map((fileName) => relative(workspaceRoot, fileName))
			.sort();

		expect(uncovered).toEqual([]);
	});
});
