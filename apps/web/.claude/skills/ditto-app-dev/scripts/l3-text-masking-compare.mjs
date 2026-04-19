import { chromium } from 'playwright';
import { PROTOTYPE_NORMALIZE_CSS } from './visual-audit.config.mjs';
import fs from 'fs';

const VIEWPORT = { width: 1536, height: 900 };
const REACT_URL = 'http://localhost:5173/';
const PROTO_URL = 'http://localhost:8888/page-home.html';

async function main() {
  const { PNG } = await import('pngjs');

  const browser = await chromium.launch({ channel: 'chromium' });
  
  // Prototype screenshot
  const protoCtx = await browser.newContext({ viewport: VIEWPORT });
  const protoPage = await protoCtx.newPage();
  await protoPage.goto(PROTO_URL, { waitUntil: 'networkidle' });
  await protoPage.addStyleTag({ content: PROTOTYPE_NORMALIZE_CSS });
  await protoPage.waitForFunction(() => document.fonts.ready);
  await protoPage.waitForTimeout(500);
  await protoPage.screenshot({ path: '/tmp/proto-l3.png', fullPage: false });

  // React screenshot
  const reactCtx = await browser.newContext({ viewport: VIEWPORT });
  const reactPage = await reactCtx.newPage();
  await reactPage.goto(REACT_URL, { waitUntil: 'networkidle' });
  await reactPage.waitForFunction(() => document.fonts.ready);
  await reactPage.waitForTimeout(500);
  await reactPage.screenshot({ path: '/tmp/react-l3.png', fullPage: false });
  
  await browser.close();

  // Now mask ALL text content on both sides and re-compare
  // Strategy: mask pixels that are bright on dark background (text pixels)
  const protoPng = PNG.sync.read(fs.readFileSync('/tmp/proto-l3.png'));
  const reactPng = PNG.sync.read(fs.readFileSync('/tmp/react-l3.png'));
  
  const width = protoPng.width;
  const height = protoPng.height;
  const totalPixels = width * height;

  let totalDiff = 0;
  let textMaskedDiff = 0;
  let textPixels = 0;
  let bgOnlyDiff = 0;
  let bgPixels = 0;

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = (y * width + x) * 4;
      
      // Check if this pixel is "text-like" (bright on dark background)
      const pAvg = (protoPng.data[idx] + protoPng.data[idx+1] + protoPng.data[idx+2]) / 3;
      const rAvg = (reactPng.data[idx] + reactPng.data[idx+1] + reactPng.data[idx+2]) / 3;
      const isTextProto = pAvg > 140;
      const isTextReact = rAvg > 140;
      const isText = isTextProto || isTextReact;
      
      const dr = Math.abs(protoPng.data[idx] - reactPng.data[idx]);
      const dg = Math.abs(protoPng.data[idx+1] - reactPng.data[idx+1]);
      const db = Math.abs(protoPng.data[idx+2] - reactPng.data[idx+2]);
      const pixelDiff = dr + dg + db;
      
      if (isText) {
        textPixels++;
        if (pixelDiff > 30) textMaskedDiff++;
      } else {
        bgPixels++;
        if (pixelDiff > 30) bgOnlyDiff++;
      }
      
      if (pixelDiff > 30) totalDiff++;
    }
  }

  console.log('=== L3 Diff Decomposition: Text vs Background ===\n');
  console.log(`Total pixels:         ${totalPixels}`);
  console.log(`Total diff pixels:     ${totalDiff} (${(totalDiff/totalPixels*100).toFixed(2)}%)`);
  console.log('');
  console.log(`Text-like pixels:      ${textPixels} (${(textPixels/totalPixels*100).toFixed(1)}%)`);
  console.log(`  Text diff pixels:    ${textMaskedDiff} (${(textMaskedDiff/textPixels*100).toFixed(1)}% of text, ${(textMaskedDiff/totalPixels*100).toFixed(2)}% of total)`);
  console.log('');
  console.log(`Background pixels:     ${bgPixels} (${(bgPixels/totalPixels*100).toFixed(1)}%)`);
  console.log(`  BG diff pixels:      ${bgOnlyDiff} (${(bgOnlyDiff/bgPixels*100).toFixed(1)}% of bg, ${(bgOnlyDiff/totalPixels*100).toFixed(2)}% of total)`);
  console.log('');
  console.log('=== Interpretation ===');
  console.log('Text diff = content rendering (font fallback, different mock data strings, icon SVGs)');
  console.log('BG diff = visual effects (glows, gradients, frosted glass, subtle shading)');
  console.log('');
  const bgRatio = bgOnlyDiff / bgPixels;
  console.log(`Background-only diff ratio: ${(bgRatio*100).toFixed(4)}%`);
  console.log(`BG-only match: ${((1-bgRatio)*100).toFixed(2)}%`);
  console.log(`BG threshold (<2%): ${bgRatio < 0.02 ? 'PASS' : 'FAIL'}`);
}

main().catch(console.error);
