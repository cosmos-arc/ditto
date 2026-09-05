#!/usr/bin/env bun
/**
 * L3 Pixel-level screenshot comparison with diff image output.
 * Usage: bun scripts/l3-pixel-diff.mjs <prototype.png> <react.png> [--threshold 0.1]
 *
 * Uses pixelmatch v7 with diffMask=true so only mismatched pixels are drawn.
 * Pass threshold: maxDiffPixelRatio < 0.02 (2%)
 */

import { createReadStream, createWriteStream } from "node:fs";
import { dirname, join } from "node:path";
import pixelmatch from "pixelmatch";
import { PNG } from "pngjs";

function loadPNG(path) {
	return new Promise((resolve, reject) => {
		createReadStream(path)
			.pipe(new PNG())
			.on("parsed", function () {
				resolve({ width: this.width, height: this.height, data: this.data });
			})
			.on("error", reject);
	});
}

function savePNG(path, width, height, data) {
	return new Promise((resolve, reject) => {
		const png = new PNG({ width, height });
		png.data = Buffer.from(data);
		png.pack().pipe(createWriteStream(path)).on("finish", resolve).on("error", reject);
	});
}

const protoPath = process.argv[2];
const reactPath = process.argv[3];
let threshold = 0.1;

for (let i = 4; i < process.argv.length; i++) {
	if (process.argv[i] === "--threshold") threshold = Number.parseFloat(process.argv[++i]);
}

if (!protoPath || !reactPath) {
	console.error("Usage: bun scripts/l3-pixel-diff.mjs <prototype.png> <react.png> [--threshold 0.1]");
	process.exit(1);
}

const outDir = dirname(protoPath);
const { width, height } = await loadPNG(protoPath);
const totalPixels = width * height;

console.log(`Comparing ${width}x${height} screenshots (threshold=${threshold})...`);

// Load both images
const [proto, react] = await Promise.all([loadPNG(protoPath), loadPNG(reactPath)]);

if (proto.width !== react.width || proto.height !== react.height) {
	console.error(`Dimension mismatch: ${proto.width}x${proto.height} vs ${react.width}x${react.height}`);
	process.exit(1);
}

// Copy to fresh arrays (pngjs Buffer may share underlying memory)
const protoPixels = new Uint8Array(totalPixels * 4);
const reactPixels = new Uint8Array(totalPixels * 4);
protoPixels.set(proto.data);
reactPixels.set(react.data);

// diffMask=true: only mismatched pixels get drawn (alpha>0), matching pixels stay transparent
const diff = Buffer.alloc(totalPixels * 4);
const mismatchedPixels = pixelmatch(protoPixels, reactPixels, diff, width, height, {
	threshold,
	diffMask: true,
});

const diffRatio = mismatchedPixels / totalPixels;
const pass = diffRatio < 0.02;

// Generate diff visualization: red dots on dimmed prototype background
const diffVis = new Uint8Array(totalPixels * 4);
for (let i = 0; i < totalPixels; i++) {
	const idx = i * 4;
	if (diff[idx + 3] > 0) {
		// Mismatched → bright red
		diffVis[idx] = 255;
		diffVis[idx + 1] = 50;
		diffVis[idx + 2] = 50;
		diffVis[idx + 3] = 255;
	} else {
		// Matched → dimmed prototype
		diffVis[idx] = Math.round(proto.data[idx] * 0.35);
		diffVis[idx + 1] = Math.round(proto.data[idx + 1] * 0.35);
		diffVis[idx + 2] = Math.round(proto.data[idx + 2] * 0.35);
		diffVis[idx + 3] = 255;
	}
}

await savePNG(join(outDir, "diff.png"), width, height, diffVis);

// Analyze by vertical band
const bandH = 100;
console.log(`\nDiff by vertical band:`);
for (let y = 0; y < height; y += bandH) {
	let bDiff = 0;
	let bTotal = 0;
	for (let dy = 0; dy < bandH && y + dy < height; dy++) {
		for (let x = 0; x < width; x++) {
			bTotal++;
			if (diff[((y + dy) * width + x) * 4 + 3] > 0) bDiff++;
		}
	}
	const ratio = bDiff / bTotal;
	if (ratio > 0.001) {
		const pct = (ratio * 100).toFixed(2).padStart(6);
		const marker = ratio > 0.05 ? "⚠" : ratio > 0.02 ? "~" : "  ";
		console.log(`  ${marker} y=${String(y).padStart(3)}-${String(y + bandH).padStart(3)}: ${pct}% (${bDiff.toLocaleString()} px)`);
	}
}

console.log(`\nL3 Results:`);
console.log(`  Mismatched: ${mismatchedPixels.toLocaleString()} / ${totalPixels.toLocaleString()} = ${(diffRatio * 100).toFixed(4)}%`);
console.log(`  Threshold:  ${threshold} per-pixel, 2% overall`);
console.log(`  Pass:       ${pass ? "YES ✓" : "NO ✗"}`);
console.log(`  Diff image: ${join(outDir, "diff.png")}`);
