import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { isDeepStrictEqual } from "node:util";

/** Verify the prepared workspace without resolving, installing or writing locks. */
export function checkWorkspace(root) {
	const manifest = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));
	if (`bun@${Bun.version}` !== manifest.packageManager) {
		throw new Error(`Bun mismatch: expected ${manifest.packageManager}, got bun@${Bun.version}`);
	}
	const lock = Bun.JSONC.parse(readFileSync(resolve(root, "bun.lock"), "utf8"));
	const workspaces = ["", ...manifest.workspaces];
	if (!isDeepStrictEqual(Object.keys(lock.workspaces).sort(), workspaces.toSorted())) {
		throw new Error("bun.lock workspace list differs from package.json");
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
			const installed = JSON.parse(readFileSync(resolve(directory, "node_modules", name, "package.json"), "utf8"));
			const entry = lock.packages[`${pkg.name}/${name}`] ?? lock.packages[name];
			if (!entry || entry[0] !== `${name}@${installed.version}`) {
				throw new Error(`Installed ${name} differs from bun.lock; run the explicit bootstrap`);
			}
		}
	}
}

if (import.meta.main) checkWorkspace(resolve(import.meta.dir, "../.."));
