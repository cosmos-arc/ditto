const colorDeclarationProperties = new Set([
	"accent-color",
	"background",
	"background-color",
	"border",
	"border-block",
	"border-block-color",
	"border-bottom",
	"border-bottom-color",
	"border-color",
	"border-inline",
	"border-inline-color",
	"border-left",
	"border-left-color",
	"border-right",
	"border-right-color",
	"border-top",
	"border-top-color",
	"box-shadow",
	"caret-color",
	"color",
	"fill",
	"outline",
	"outline-color",
	"stroke",
	"text-decoration",
	"text-decoration-color",
	"text-shadow",
]);

function isColorDeclarationProperty(property: string): boolean {
	const normalized = property.trim().toLowerCase();
	if (colorDeclarationProperties.has(normalized)) return true;

	return normalized.endsWith("-shadow") || normalized.endsWith("-color");
}

function stripNonColorReferences(value: string): string {
	return value
		.replace(/url\([^)]*\)/gi, " ")
		.replace(/'[^']*'|"[^"]*"/g, " ");
}

export function findHardcodedColors(source: string): string[] {
	const hits: string[] = [];
	const declarationPattern = /(^|[;{\s])([a-z-]+)\s*:\s*([^;{}]+)/gi;

	for (const match of source.matchAll(declarationPattern)) {
		const property = match[2];
		if (!isColorDeclarationProperty(property)) continue;

		const value = stripNonColorReferences(match[3]);

		for (const hexMatch of value.matchAll(/#[0-9a-f]{3}(?:[0-9a-f]{3})?(?:[0-9a-f]{2})?\b/gi)) {
			hits.push(hexMatch[0]);
		}

		for (const functionalColorMatch of value.matchAll(/\b(?:rgba?|hsla?)\s*\(/gi)) {
			hits.push(functionalColorMatch[0].replace(/\s+/g, "").toLowerCase());
		}

		if (/\boklch\(/i.test(value) && !/\boklch\(\s*from\s+var\(/i.test(value)) {
			hits.push("oklch(");
		}
	}

	return hits;
}
