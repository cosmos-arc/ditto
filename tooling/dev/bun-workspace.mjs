import { existsSync, realpathSync, readFileSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { isDeepStrictEqual } from "node:util";

function installedPackage(directory, name, root) {
	for (let current = directory; ; current = dirname(current)) {
		const path = resolve(current, "node_modules", name, "package.json");
		if (existsSync(path)) {
			const installed = realpathSync(path);
			const local = relative(root, installed);
			if (local === ".." || local.startsWith(`..${sep}`) || isAbsolute(local)) {
				throw new Error(`Dependency ${name} escapes the current workspace`);
			}
			return installed;
		}
		if (current === root || dirname(current) === current) throw new Error(`Missing installed dependency: ${name}`);
	}
}

function supportsPlatform(metadata) {
	return [[metadata.os, process.platform], [metadata.cpu, process.arch]].every(([value, actual]) => {
		const values = value === undefined ? [] : Array.isArray(value) ? value : [value];
		return !values.includes(`!${actual}`) && (!values.some((item) => !item.startsWith("!")) || values.includes(actual));
	});
}

/** Verify the prepared workspace without resolving, installing or writing locks. */
export function checkWorkspace(root) {
	root = realpathSync(root);
	const manifest = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));
	if (`bun@${Bun.version}` !== manifest.packageManager) {
		throw new Error(`Bun mismatch: expected ${manifest.packageManager}, got bun@${Bun.version}`);
	}
	const lock = Bun.JSONC.parse(readFileSync(resolve(root, "bun.lock"), "utf8"));
	const workspaces = ["", ...manifest.workspaces];
	if (!isDeepStrictEqual(Object.keys(lock.workspaces).sort(), workspaces.toSorted())) {
		throw new Error("bun.lock workspace list differs from package.json");
	}
	const visited = new Set();
	function verifyDependency(directory, name, parentKey) {
		let scope = parentKey;
		while (scope && !lock.packages[`${scope}/${name}`]) scope = scope.replace(/(?:^|\/)(?:@[^/]+\/)?[^/]+$/, "");
		const key = scope ? `${scope}/${name}` : name;
		const entry = lock.packages[key];
		if (!entry) throw new Error(`Missing bun.lock dependency: ${name}`);
		if (!supportsPlatform(entry[2] ?? {})) return;
		const path = installedPackage(directory, name, root);
		const installed = JSON.parse(readFileSync(path, "utf8"));
		if (entry[0] !== `${name}@${installed.version}`) {
			throw new Error(`Installed ${name} differs from bun.lock; run the explicit bootstrap`);
		}
		if (visited.has(path)) return;
		visited.add(path);
		const metadata = entry[2] ?? {};
		const requiredPeers = Object.fromEntries(Object.entries(metadata.peerDependencies ?? {}).filter(([name]) => !(metadata.optionalPeers ?? []).includes(name)));
		for (const dependency of Object.keys({ ...requiredPeers, ...metadata.dependencies, ...metadata.optionalDependencies })) {
			verifyDependency(dirname(path), dependency, key);
		}
	}
	for (const workspace of workspaces) {
		const directory = resolve(root, workspace);
		const pkg = JSON.parse(readFileSync(resolve(directory, "package.json"), "utf8"));
		for (const field of ["dependencies", "devDependencies", "optionalDependencies", "peerDependencies"]) {
			if (!isDeepStrictEqual(pkg[field] ?? {}, lock.workspaces[workspace][field] ?? {})) {
				throw new Error(`bun.lock is stale: ${workspace || "."} ${field}`);
			}
		}
		for (const name of Object.keys({ ...pkg.dependencies, ...pkg.devDependencies })) {
			verifyDependency(directory, name, pkg.name);
		}
	}
}

if (import.meta.main) checkWorkspace(resolve(import.meta.dir, "../.."));
