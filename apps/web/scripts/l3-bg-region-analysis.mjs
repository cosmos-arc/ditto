import fs from 'fs';

const { PNG } = await import('pngjs');
const protoPng = PNG.sync.read(fs.readFileSync('/tmp/proto-l3.png'));
const reactPng = PNG.sync.read(fs.readFileSync('/tmp/react-l3.png'));

const width = protoPng.width;
const height = protoPng.height;

// Define smaller regions for pinpointing
const REGIONS = [
  // Top strip areas
  { name: 'Rail (0-56)', x: 0, y: 0, w: 56, h: 900 },
  { name: 'Header (56-1536, 0-68)', x: 56, y: 0, w: 1480, h: 68 },
  { name: 'Pulse Strip (56-1536, 68-100)', x: 56, y: 68, w: 1480, h: 32 },
  // Main content - split into quarters
  { name: 'Main-TopLeft', x: 56, y: 100, w: 580, h: 200 },
  { name: 'Main-TopRight', x: 636, y: 100, w: 580, h: 200 },
  { name: 'Main-MidLeft', x: 56, y: 300, w: 580, h: 200 },
  { name: 'Main-MidRight', x: 636, y: 300, w: 580, h: 200 },
  { name: 'Main-BotLeft', x: 56, y: 500, w: 580, h: 400 },
  { name: 'Main-BotRight', x: 636, y: 500, w: 580, h: 400 },
  // Sidebar
  { name: 'Sidebar-Top', x: 1216, y: 100, w: 320, h: 250 },
  { name: 'Sidebar-Mid', x: 1216, y: 350, w: 320, h: 250 },
  { name: 'Sidebar-Bot', x: 1216, y: 600, w: 320, h: 300 },
];

console.log('=== Background-Only Diff by Region ===\n');
console.log(`${'Region'.padEnd(30)} ${'BG Pixels'.padStart(10)} ${'BG Diff'.padStart(8)} ${'Ratio'.padStart(10)} ${'Status'.padStart(6)}`);
console.log('-'.repeat(68));

let totalBgDiff = 0;
let totalBgPixels = 0;

for (const r of REGIONS) {
  let bgDiff = 0;
  let bgPx = 0;
  
  for (let y = r.y; y < Math.min(r.y + r.h, height); y++) {
    for (let x = r.x; x < Math.min(r.x + r.w, width); x++) {
      const idx = (y * width + x) * 4;
      const pAvg = (protoPng.data[idx] + protoPng.data[idx+1] + protoPng.data[idx+2]) / 3;
      const rAvg = (reactPng.data[idx] + reactPng.data[idx+1] + reactPng.data[idx+2]) / 3;
      
      // Skip text-like pixels
      if (pAvg > 140 || rAvg > 140) continue;
      
      bgPx++;
      const dr = Math.abs(protoPng.data[idx] - reactPng.data[idx]);
      const dg = Math.abs(protoPng.data[idx+1] - reactPng.data[idx+1]);
      const db = Math.abs(protoPng.data[idx+2] - reactPng.data[idx+2]);
      if (dr + dg + db > 30) bgDiff++;
    }
  }

  const ratio = bgPx > 0 ? bgDiff / bgPx : 0;
  totalBgDiff += bgDiff;
  totalBgPixels += bgPx;
  const status = ratio < 0.02 ? 'PASS' : ratio < 0.05 ? '~' : ratio < 0.10 ? 'MED' : 'HIGH';
  console.log(`${r.name.padEnd(30)} ${String(bgPx).padStart(10)} ${String(bgDiff).padStart(8)} ${(ratio*100).toFixed(2).padStart(9)}% ${status.padEnd(6)}`);
}

console.log('-'.repeat(68));
const totalRatio = totalBgPixels > 0 ? totalBgDiff / totalBgPixels : 0;
console.log(`${'TOTAL'.padEnd(30)} ${String(totalBgPixels).padStart(10)} ${String(totalBgDiff).padStart(8)} ${(totalRatio*100).toFixed(4).padStart(9)}% ${totalRatio < 0.02 ? 'PASS' : 'FAIL'}`);

