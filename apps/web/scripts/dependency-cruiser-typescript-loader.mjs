import { registerHooks } from "node:module";

const typescriptUrl = new URL("../node_modules/typescript/lib/typescript.js", import.meta.url).href;

registerHooks({
	resolve(specifier, context, nextResolve) {
		if (specifier === "typescript") {
			return nextResolve(typescriptUrl, context);
		}
		return nextResolve(specifier, context);
	},
});
