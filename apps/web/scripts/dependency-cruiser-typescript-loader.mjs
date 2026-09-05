import { registerHooks } from "node:module";

const typescriptUrl = new URL("../node_modules/typescript/lib/typescript.js", import.meta.url).href;

registerHooks({
	resolve(specifier, context, nextResolve) {
		if (specifier === "typescript") {
			return { shortCircuit: true, url: typescriptUrl };
		}
		return nextResolve(specifier, context);
	},
});
