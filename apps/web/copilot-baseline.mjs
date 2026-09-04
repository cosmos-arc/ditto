import { chromium } from 'playwright';
const browser = await chromium.launch({ channel: 'chromium' });
const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });
await page.goto('http://localhost:8888/page-ai-copilot.html');
await page.waitForLoadState('networkidle');

// Screenshots: all tabs + zones
await page.screenshot({ path: '/tmp/copilot-default.png', fullPage: false });
console.log('Default view saved');

// Check for tabs
const tabs = await page.evaluate(() => {
  const tabBtns = document.querySelectorAll('[data-tab-target]');
  return Array.from(tabBtns).map(t => t.getAttribute('data-tab-target'));
});
console.log('Tabs found:', tabs);

for (const tab of tabs) {
  await page.evaluate((t) => { document.querySelector(`[data-tab-target="${t}"]`).click(); }, tab);
  await page.waitForTimeout(400);
  await page.screenshot({ path: `/tmp/copilot-tab-${tab}.png`, fullPage: false });
  console.log(`Tab ${tab} saved`);
}

// States gallery
await page.evaluate(() => { document.getElementById('view-states').checked = true; });
await page.waitForTimeout(500);
await page.screenshot({ path: '/tmp/copilot-states.png', fullPage: false });
console.log('States gallery saved');

// Overlays gallery
await page.evaluate(() => { document.getElementById('view-overlays').checked = true; });
await page.waitForTimeout(500);
await page.screenshot({ path: '/tmp/copilot-overlays.png', fullPage: false });
console.log('Overlays gallery saved');

// Metrics + checks
await page.evaluate(() => { document.getElementById('view-default').checked = true; });
await page.waitForTimeout(300);

const metrics = await page.evaluate(() => {
  const items = [];
  const selectors = ['.shell-rail', '.shell-header', '.copilot-shell', '.copilot-sidebar',
    '.status-bar', '.copilot-input-area', '.copilot-messages'];
  selectors.forEach(sel => {
    const el = document.querySelector(sel);
    if (!el) return;
    const rect = el.getBoundingClientRect();
    items.push({ sel, x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) });
  });
  return items;
});
console.log('\nLayout metrics:');
metrics.forEach(m => console.log(`  ${m.sel}: ${m.w}x${m.h} at (${m.x},${m.y})`));

// Inline styles check
const inlineCount = await page.evaluate(() => document.querySelectorAll('[style]').length);
console.log(`\nJS-injected inline styles: ${inlineCount}`);

// VP overflow
const vp = await page.evaluate(() => ({
  scrollH: document.documentElement.scrollHeight,
  clientH: document.documentElement.clientHeight,
  overflow: document.documentElement.scrollHeight > document.documentElement.clientHeight,
}));
console.log(`VP-STANDARD: scrollH=${vp.scrollH} clientH=${vp.clientH} overflow=${vp.overflow}`);

// VP-COMPACT
await page.setViewportSize({ width: 1366, height: 768 });
await page.evaluate(() => { document.getElementById('view-default').checked = true; });
await page.waitForTimeout(300);
const compact = await page.evaluate(() => ({
  scrollH: document.documentElement.scrollHeight,
  clientH: document.documentElement.clientHeight,
  overflow: document.documentElement.scrollHeight > document.documentElement.clientHeight,
}));
await page.screenshot({ path: '/tmp/copilot-compact.png', fullPage: false });
console.log(`VP-COMPACT: scrollH=${compact.scrollH} clientH=${compact.clientH} overflow=${compact.overflow}`);

// HTML source inline style check
const resp = await fetch('http://localhost:8888/page-ai-copilot.html');
const html = await resp.text();
const sourceInline = (html.match(/style="/g) || []).length;
console.log(`HTML source inline styles: ${sourceInline}`);

// Check for status-badge reuse in tabs
const tabReuse = await page.evaluate(() => {
  const tabBtns = document.querySelectorAll('[data-tab-target]');
  return Array.from(tabBtns).some(t => t.classList.contains('ai-status-badge') || t.querySelector('.ai-status-dot'));
});
console.log(`Tab reuses status-badge: ${tabReuse}`);

await browser.close();
