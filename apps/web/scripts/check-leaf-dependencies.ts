import { readdir, readFile } from "node:fs/promises";
import { builtinModules } from "node:module";
import { dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

const dependencyFields = ["dependencies", "devDependencies", "optionalDependencies", "peerDependencies"] as const;
const sourceExtensions = new Set([".cjs", ".cts", ".js", ".jsx", ".mjs", ".mts", ".ts", ".tsx"]);
const builtins = new Set([...builtinModules, ...builtinModules.map((moduleName) => moduleName.replace(/^node:/u, ""))]);
const defaultWebRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

type JsonObject = Record<string, unknown>;

export type LeafManifestDependencyViolation = {
	readonly packageName: string;
	readonly source: string;
	readonly specifier: string;
};

export type LeafManifestDependencyAudit = {
	readonly filesChecked: number;
	readonly violations: readonly LeafManifestDependencyViolation[];
};

export type LeafManifestDependencyAuditOptions = {
	readonly webRoot?: string;
};

function isJsonObject(value: unknown): value is JsonObject {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseJsonObject(text: string, fileName: string): JsonObject {
	let value: unknown;
	try {
		value = JSON.parse(text);
	} catch (error) {
		throw new Error(`${fileName} must contain valid JSON`, { cause: error });
	}
	if (!isJsonObject(value)) {
		throw new Error(`${fileName} must contain a JSON object`);
	}
	return value;
}

function manifestDependencies(manifest: JsonObject): Set<string> {
	const dependencies = new Set<string>();
	for (const field of dependencyFields) {
		const section = manifest[field];
		if (section === undefined) continue;
		if (!isJsonObject(section)) {
			throw new Error(`package.json ${field} must be an object`);
		}
		for (const packageName of Object.keys(section)) dependencies.add(packageName);
	}
	if (typeof manifest["name"] === "string") dependencies.add(manifest["name"]);
	return dependencies;
}

function manifestImportAliases(manifest: JsonObject): string[] {
	if (manifest["imports"] === undefined) return [];
	if (!isJsonObject(manifest["imports"])) {
		throw new Error("package.json imports must be an object");
	}
	return Object.keys(manifest["imports"]);
}

async function tsconfigPathAliases(webRoot: string): Promise<string[]> {
	const configPath = join(webRoot, "tsconfig.base.json");
	let configText: string;
	try {
		configText = await readFile(configPath, "utf8");
	} catch (error) {
		if (isJsonObject(error) && error["code"] === "ENOENT") return [];
		throw error;
	}
	const parsed = ts.parseConfigFileTextToJson(configPath, configText);
	if (parsed.error !== undefined) {
		throw new Error(ts.flattenDiagnosticMessageText(parsed.error.messageText, "\n"));
	}
	const config = isJsonObject(parsed.config) ? parsed.config : {};
	const compilerOptions = isJsonObject(config["compilerOptions"]) ? config["compilerOptions"] : {};
	const paths = isJsonObject(compilerOptions["paths"]) ? compilerOptions["paths"] : {};
	return Object.keys(paths);
}

function matchesAlias(specifier: string, pattern: string): boolean {
	const wildcard = pattern.indexOf("*");
	if (wildcard === -1) return specifier === pattern;
	const prefix = pattern.slice(0, wildcard);
	const suffix = pattern.slice(wildcard + 1);
	return (
		specifier.length >= prefix.length + suffix.length && specifier.startsWith(prefix) && specifier.endsWith(suffix)
	);
}

function packageNameForSpecifier(
	specifier: string,
	aliases: readonly string[],
	selfName: string | undefined,
): string | null {
	if (
		specifier.startsWith(".") ||
		specifier.startsWith("/") ||
		specifier.startsWith("#") ||
		/^[a-z][a-z\d+.-]*:/iu.test(specifier) ||
		aliases.some((alias) => matchesAlias(specifier, alias)) ||
		builtins.has(specifier) ||
		specifier === "bun"
	) {
		return null;
	}
	const parts = specifier.split("/");
	const packageName = specifier.startsWith("@") ? parts.slice(0, 2).join("/") : (parts[0] ?? specifier);
	return packageName === selfName ? null : packageName;
}

function scriptKind(fileName: string): ts.ScriptKind {
	switch (extname(fileName)) {
		case ".jsx":
			return ts.ScriptKind.JSX;
		case ".tsx":
			return ts.ScriptKind.TSX;
		case ".js":
		case ".cjs":
		case ".mjs":
			return ts.ScriptKind.JS;
		default:
			return ts.ScriptKind.TS;
	}
}

function literalText(node: ts.Node | undefined): string | null {
	return node !== undefined && ts.isStringLiteralLike(node) ? node.text : null;
}

function importSpecifiers(fileName: string, sourceText: string): string[] {
	const source = ts.createSourceFile(fileName, sourceText, ts.ScriptTarget.Latest, true, scriptKind(fileName));
	const specifiers = new Set<string>();
	const add = (value: string | null): void => {
		if (value !== null) specifiers.add(value);
	};
	const visit = (node: ts.Node): void => {
		if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
			add(literalText(node.moduleSpecifier));
		} else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)) {
			add(literalText(node.moduleReference.expression));
		} else if (ts.isImportTypeNode(node) && ts.isLiteralTypeNode(node.argument)) {
			add(literalText(node.argument.literal));
		} else if (ts.isCallExpression(node)) {
			const directImport = node.expression.kind === ts.SyntaxKind.ImportKeyword;
			const directRequire = ts.isIdentifier(node.expression) && node.expression.text === "require";
			const requireResolve =
				ts.isPropertyAccessExpression(node.expression) &&
				ts.isIdentifier(node.expression.expression) &&
				node.expression.expression.text === "require" &&
				node.expression.name.text === "resolve";
			if (directImport || directRequire || requireResolve) add(literalText(node.arguments[0]));
		}
		ts.forEachChild(node, visit);
	};
	visit(source);
	return [...specifiers].sort((left, right) => left.localeCompare(right));
}

async function sourceFiles(directory: string): Promise<string[]> {
	const entries = await readdir(directory, { withFileTypes: true }).catch((error: unknown) => {
		if (isJsonObject(error) && error["code"] === "ENOENT") return [];
		throw error;
	});
	const files: string[] = [];
	for (const entry of entries) {
		const absolute = join(directory, entry.name);
		if (entry.isDirectory()) {
			files.push(...(await sourceFiles(absolute)));
		} else if (entry.isFile() && sourceExtensions.has(extname(entry.name))) {
			files.push(absolute);
		}
	}
	return files;
}

async function checkedFiles(webRoot: string): Promise<string[]> {
	const files = [...(await sourceFiles(join(webRoot, "src"))), ...(await sourceFiles(join(webRoot, "scripts")))];
	for (const entry of await readdir(webRoot, { withFileTypes: true })) {
		if (entry.isFile() && sourceExtensions.has(extname(entry.name))) {
			files.push(join(webRoot, entry.name));
		}
	}
	return [...new Set(files)].sort((left, right) => left.localeCompare(right));
}

export async function auditLeafManifestDependencies(
	options: LeafManifestDependencyAuditOptions = {},
): Promise<LeafManifestDependencyAudit> {
	const webRoot = resolve(options.webRoot ?? defaultWebRoot);
	const manifest = parseJsonObject(await readFile(join(webRoot, "package.json"), "utf8"), "package.json");
	const declared = manifestDependencies(manifest);
	const selfName = typeof manifest["name"] === "string" ? manifest["name"] : undefined;
	const aliases = [...manifestImportAliases(manifest), ...(await tsconfigPathAliases(webRoot))];
	const files = await checkedFiles(webRoot);
	const violations: LeafManifestDependencyViolation[] = [];
	for (const file of files) {
		const source = relative(webRoot, file).split("\\").join("/");
		for (const specifier of importSpecifiers(file, await readFile(file, "utf8"))) {
			const packageName = packageNameForSpecifier(specifier, aliases, selfName);
			if (packageName !== null && !declared.has(packageName)) {
				violations.push({ packageName, source, specifier });
			}
		}
	}
	violations.sort(
		(left, right) => left.source.localeCompare(right.source) || left.specifier.localeCompare(right.specifier),
	);
	return { filesChecked: files.length, violations };
}

function formatViolation(violation: LeafManifestDependencyViolation): string {
	return `${violation.source}: package ${JSON.stringify(violation.packageName)} imported via ${JSON.stringify(violation.specifier)} is not declared in apps/web/package.json`;
}

async function main(): Promise<void> {
	const audit = await auditLeafManifestDependencies();
	if (audit.violations.length > 0) {
		process.stderr.write(`${audit.violations.map(formatViolation).join("\n")}\n`);
		process.exitCode = 1;
		return;
	}
	process.stdout.write(`Web leaf manifest dependency check passed (${audit.filesChecked} files).\n`);
}

const entryPoint = process.argv[1];
if (entryPoint !== undefined && pathToFileURL(resolve(entryPoint)).href === import.meta.url) {
	void main().catch((error: unknown) => {
		process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
		process.exitCode = 1;
	});
}
