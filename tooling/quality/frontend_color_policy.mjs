const RAW_COLOR_PATTERNS = [
	{ syntax: "hex", pattern: /#[0-9a-fA-F]{3,8}\b/gu },
	{ syntax: "rgb", pattern: /\brgba?\s*\(/giu },
	{ syntax: "hsl", pattern: /\bhsla?\s*\(/giu },
	{ syntax: "oklab", pattern: /\boklab\s*\(/giu },
	{ syntax: "oklch", pattern: /\boklch\s*\(/giu },
];

function withoutComments(source) {
	return source.replace(/\/\*[\s\S]*?\*\//gu, (comment) => comment.replace(/[^\n]/gu, " "));
}

export function findRawColorPrimitives(source, filePath) {
	const searchable = withoutComments(source);
	const findings = [];
	for (const { syntax, pattern } of RAW_COLOR_PATTERNS) {
		pattern.lastIndex = 0;
		for (const match of searchable.matchAll(pattern)) {
			const index = match.index ?? 0;
			findings.push({
				filePath,
				index,
				line: searchable.slice(0, index).split("\n").length,
				syntax,
				value: match[0],
			});
		}
	}
	return findings.sort((left, right) => left.index - right.index);
}

export function isCanonicalTokenFile(relativeWebPath) {
	const normalized = relativeWebPath.replaceAll("\\", "/");
	return normalized.startsWith("src/styles/design-tokens/") && normalized.endsWith(".css");
}
