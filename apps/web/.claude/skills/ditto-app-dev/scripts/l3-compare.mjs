import { chromium } from 'playwright';
import { PROTOTYPE_NORMALIZE_CSS } from './visual-audit.config.mjs';
import fs from 'fs';

const VIEWPORT = { width: 1536, height: 900 };
const REACT_URL = 'http://localhost:5173/';
const PROTO_URL = 'http://localhost:8888/docs/designs/specs/prototypes/page-home.html';

async function main() {
  const browser = await chromium.launch({ channel: 'chromium' });

  const protoCtx = await browser.newContext({ viewport: VIEWPORT });
  const protoPage = await protoCtx.newPage();
  await protoPage.goto(PROTO_URL, { waitUntil: 'networkidle' });
  await protoPage.addStyleTag({ content: PROTOTYPE_NORMALIZE_CSS });
  await protoPage.waitForFunction(() => document.fonts.ready);
  await protoPage.waitForTimeout(500);
  await protoPage.screenshot({ path: '/tmp/proto-l3.png', fullPage: false });
  console.log('Prototype screenshot done');

  const reactCtx = await browser.newContext({ viewport: VIEWPORT });
  const reactPage = await reactCtx.newPage();
  await reactPage.goto(REACT_URL, { waitUntil: 'networkidle' });
  await reactPage.waitForFunction(() => document.fonts.ready);
  await reactPage.waitForTimeout(500);
  await reactPage.screenshot({ path: '/tmp/react-l3.png', fullPage: false });
  console.log('React screenshot done');

  await browser.close();

  // Pixel comparison using raw buffer analysis
  const protoBuf = fs.readFileSync('/tmp/proto-l3.png');
  const reactBuf = fs.readFileSync('/tmp/react-l3.png');
  
  // Parse PNG manually (simplified: use pngjs)
  const { PNG } = await import('pngjs');
  const protoPng = PNG.sync.read(protoBuf);
  const reactPng = PNG.sync.read(reactBuf);

  const width = Math.min(protoPng.width, reactPng.width);
  const height = Math.min(protoPng.height, reactPng.height);
  const totalPixels = width * height;

  let diffPixels = 0;
  let totalDiff = 0;
  const maxChannelDiff = 255 * 3;

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = (y * width + x) * 4;
      const dr = Math.abs(protoPng.data[idx] - reactPng.data[idx]);
      const dg = Math.abs(protoPng.data[idx+1] - reactPng.data[idx+1]);
      const db = Math.abs(protoPng.data[idx+2] - reactPng.data[idx+2]);
      const pixelDiff = dr + dg + db;
      if (pixelDiff > 30) diffPixels++;
      totalDiff += pixelDiff / maxChannelDiff;
    }
  }

  const diffPixelRatio = diffPixels / totalPixels;
  const matchPercent = ((1 - diffPixelRatio) * 100).toFixed(2);

  console.log(`\n=== L3 Pixel Comparison ===`);
  console.log(`Resolution: ${width}x${height}`);
  console.log(`Total pixels: ${totalPixels}`);
  console.log(`Different pixels: ${diffPixels}`);
  console.log(`Diff ratio: ${(diffPixelRatio * 100).toFixed(4)}%`);
  console.log(`Match: ${matchPercent}%`);
  console.log(`Threshold: <2%`);
  console.log(`Result: ${diffPixelRatio < 0.02 ? 'PASS ✓' : 'FAIL ✗'}`);

  // Diff heatmap
  const diffPng = new PNG({ width, height });
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = (y * width + x) * 4;
      const dr = Math.abs(protoPng.data[idx] - reactPng.data[idx]);
      const dg = Math.abs(protoPng.data[idx+1] - reactPng.data[idx+1]);
      const db = Math.abs(protoPng.data[idx+2] - reactPng.data[idx+2]);
      if (dr + dg + db > 30) {
        diffPng.data[idx] = 255; diffPng.data[idx+1] = 0; diffPng.data[idx+2] = 255; diffPng.data[idx+3] = 200;
      } else {
        diffPng.data[idx] = 40; diffPng.data[idx+1] = 40; diffPng.data[idx+2] = 40; diffPng.data[idx+3] = 255;
      }
    }
  }
  fs.writeFileSync('/tmp/l3-diff.png', PNG.sync.write(diffPng));
  console.log(`Diff heatmap: /tmp/l3-diff.png`);
}

main().catch(console.error);
