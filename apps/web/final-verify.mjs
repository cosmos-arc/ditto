import { chromium } from 'playwright';
async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });

  for (const [url, label] of [['/', 'Home'], ['/markets', 'Markets'], ['/research', 'Research'], ['/trading', 'Trading'], ['/platform', 'Platform']]) {
    const page = await ctx.newPage();
    await page.goto(`http://localhost:5173${url}`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1500);

    const data = await page.evaluate(() => {
      const h1 = document.querySelector('header h1');
      const headerAfter = document.querySelector('header') ? getComputedStyle(document.querySelector('header'), '::after') : null;
      const pulseStrip = document.querySelector('[data-slot="pulse-strip"], [data-slot="session-strip"]');
      const decisionBanner = document.querySelector('[data-slot="decision-banner"]');
      const fontData = document.querySelector('.font-data');

      return {
        title: h1?.textContent ?? 'NO TITLE',
        headerAfterBg: headerAfter?.background?.includes('oklch(0.78 0.06 74') ? 'brass ✅' : 'not brass',
        hasPulseGlow: pulseStrip ? getComputedStyle(pulseStrip).boxShadow !== 'none' : false,
        hasBannerBorder: decisionBanner ? getComputedStyle(decisionBanner).borderLeft !== 'none' && getComputedStyle(decisionBanner).borderLeftWidth !== '0px' : false,
        fontDataMono: fontData ? getComputedStyle(fontData).fontFamily.includes('JetBrains Mono') : false,
        panels: document.querySelectorAll('[data-slot="panel"]').length,
      };
    });
    console.log(`\n=== ${label} (${url}) ===`);
    console.log(JSON.stringify(data, null, 2));
    await page.close();
  }

  await browser.close();
  console.log('\n✅ Verification complete.');
}
main().catch(e => { console.error(e); process.exit(1); });
