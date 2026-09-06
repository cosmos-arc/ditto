import { registerHooks } from "node:module";
import { fileURLToPath } from "node:url";

const typescriptPath = fileURLToPath(new URL("../node_modules/typescript/lib/typescript.js", import.meta.url));

registerHooks({
	resolve(specifier, context, nextResolve) {
		if (specifier === "typescript") {
			return nextResolve(typescriptPath, context);
		}
		return nextResolve(specifier, context);
	},
});
