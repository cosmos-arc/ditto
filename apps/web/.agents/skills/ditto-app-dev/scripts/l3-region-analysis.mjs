import { chromium } from 'playwright';
import { PROTOTYPE_NORMALIZE_CSS } from './visual-audit.config.mjs';
import fs from 'fs';

const VIEWPORT = { width: 1536, height: 900 };

// Define regions based on the prototype layout (from metrics.json)
const REGIONS = [
  { name: 'Rail', x: 0, y: 0, w: 56, h: 900 },
  { name: 'Header', x: 56, y: 0, w: 1480, h: 68 },
  { name: 'Pulse Strip', x: 56, y: 68, w: 1480, h: 32 },
  { name: 'Main Area', x: 56, y: 100, w: 1160, h: 800 },
  { name: 'Sidebar', x: 1216, y: 100, w: 320, h: 800 },
  { name: 'Decision Banner', x: 72, y: 100, w: 1128, h: 170 },
  { name: 'Priority Queue', x: 72, y: 270, w: 1128, h: 200 },
  { name: 'Secondary (bottom)', x: 72, y: 470, w: 1128, h: 430 },
  { name: 'Sidebar Top', x: 1216, y: 100, w: 320, h: 350 },
  { name: 'Sidebar Bottom', x: 1216, y: 450, w: 320, h: 450 },
];

async function main() {
  const { PNG } = await import('pngjs');
  const protoPng = PNG.sync.read(fs.readFileSync('/tmp/proto-l3.png'));
  const reactPng = PNG.sync.read(fs.readFileSync('/tmp/react-l3.png'));

  const width = protoPng.width;
  const height = protoPng.height;

  console.log('=== L3 Region-by-Region Diff Analysis ===\n');
  console.log(`${'Region'.padEnd(25)} ${'Pixels'.padStart(10)} ${'Diff'.padStart(8)} ${'Ratio'.padStart(10)} ${'Match'.padStart(8)}`);
  console.log('-'.repeat(65));

  let totalDiff = 0;
  let totalPixels = 0;

  for (const r of REGIONS) {
    let regionDiff = 0;
    let regionTotal = 0;

    for (let y = r.y; y < Math.min(r.y + r.h, height); y++) {
      for (let x = r.x; x < Math.min(r.x + r.w, width); x++) {
        const idx = (y * width + x) * 4;
        const dr = Math.abs(protoPng.data[idx] - reactPng.data[idx]);
        const dg = Math.abs(protoPng.data[idx+1] - reactPng.data[idx+1]);
        const db = Math.abs(protoPng.data[idx+2] - reactPng.data[idx+2]);
        regionTotal++;
        if (dr + dg + db > 30) regionDiff++;
      }
    }

    const ratio = regionDiff / regionTotal;
    totalDiff += regionDiff;
    totalPixels += regionTotal;
    const pct = (ratio * 100).toFixed(2);
    const match = ((1 - ratio) * 100).toFixed(1);
    const status = ratio < 0.02 ? '✓' : ratio < 0.10 ? '~' : '✗';
    console.log(`${r.name.padEnd(25)} ${String(regionTotal).padStart(10)} ${String(regionDiff).padStart(8)} ${pct.padStart(9)}% ${match.padStart(7)}% ${status}`);
  }

  const totalRatio = totalDiff / totalPixels;
  console.log('-'.repeat(65));
  console.log(`${'TOTAL'.padEnd(25)} ${String(totalPixels).padStart(10)} ${String(totalDiff).padStart(8)} ${(totalRatio*100).toFixed(4).padStart(9)}% ${((1-totalRatio)*100).toFixed(1).padStart(7)}%`);

  // Now analyze diff content - classify by type
  console.log('\n=== Diff Root Cause Classification ===\n');

  // Sample pixels in diff areas to understand what's different
  const diffSamples = [];
  for (let y = 0; y < height; y += 4) {
    for (let x = 0; x < width; x += 4) {
      const idx = (y * width + x) * 4;
      const dr = Math.abs(protoPng.data[idx] - reactPng.data[idx]);
      const dg = Math.abs(protoPng.data[idx+1] - reactPng.data[idx+1]);
      const db = Math.abs(protoPng.data[idx+2] - reactPng.data[idx+2]);
      if (dr + dg + db > 30) {
        diffSamples.push({ x, y, pr: protoPng.data[idx], pg: protoPng.data[idx+1], pb: protoPng.data[idx+2],
          rr: reactPng.data[idx], rg: reactPng.data[idx+1], rb: reactPng.data[idx+2] });
      }
    }
  }

  // Classify: text area vs background vs effect
  let textDiffs = 0;
  let bgDiffs = 0;
  let effectDiffs = 0;

  for (const s of diffSamples) {
    const pLum = (s.pr + s.pg + s.pb) / 3;
    const rLum = (s.rr + s.rg + s.rb) / 3;
    const lumDiff = Math.abs(pLum - rLum);

    // Text-like: either side is bright on dark (high contrast)
    if (pLum > 150 || rLum > 150) {
      textDiffs++;
    } else if (lumDiff > 10) {
      effectDiffs++; // Background with significant luminance change = visual effect
    } else {
      bgDiffs++;
    }
  }

  console.log(`Sampled diff pixels: ${diffSamples.length}`);
  console.log(`  Text/content diffs:     ${textDiffs} (${(textDiffs/diffSamples.length*100).toFixed(1)}%)`);
  console.log(`  Background diffs:       ${bgDiffs} (${(bgDiffs/diffSamples.length*100).toFixed(1)}%)`);
  console.log(`  Visual effect diffs:    ${effectDiffs} (${(effectDiffs/diffSamples.length*100).toFixed(1)}%)`);
}

main().catch(console.error);
