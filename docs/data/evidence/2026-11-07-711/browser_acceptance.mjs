import {chromium} from '../../../../node_modules/playwright/index.mjs';
import {writeFile,mkdir} from 'node:fs/promises';
const root=new URL('.',import.meta.url).pathname;
const report={started_at:new Date().toISOString(),routes:[]};
const browser=await chromium.launch({headless:true});
try {
 for(const [name,id] of [['stock',1000001],['etf',2001562]]) {
  const page=await browser.newPage({viewport:{width:1440,height:1080},acceptDownloads:true});
  const seen=new Map();const key=(p)=>`${p.adjustment}:${p.period}:${p.start_date}:${p.end_date}:${p.allow_experimental_data}`;
  page.on('response',r=>{if(r.url().endsWith('/market/chart'))seen.set(key(r.request().postDataJSON()),r)});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let initial=page.waitForEvent('requestfinished',{predicate:r=>r.url().endsWith('/market/chart'),timeout:60000}).catch(()=>null);
  await page.goto(`http://127.0.0.1:15171/instruments/${id}?tab=chart`,{waitUntil:'domcontentloaded'});
  await initial; console.log(name,'initial finished');
  let changed=page.waitForResponse(r=>r.url().endsWith('/market/chart')&&r.request().postDataJSON()?.start_date==='2026-10-01',{timeout:120000});
  await page.getByLabel('开始日期',{exact:true}).fill('2026-10-01');
  await changed;console.log(name,'start changed');
  changed=page.waitForResponse(r=>r.url().endsWith('/market/chart')&&r.request().postDataJSON()?.end_date==='2026-11-06',{timeout:120000});
  await page.getByLabel('截至日期',{exact:true}).fill('2026-11-06');
  await changed;console.log(name,'end changed');
  let response=page.waitForResponse(r=>r.url().endsWith('/market/chart')&&r.request().postDataJSON()?.allow_experimental_data===true&&r.request().postDataJSON()?.start_date==='2026-10-01'&&r.request().postDataJSON()?.end_date==='2026-11-06',{timeout:120000});
  await page.getByTestId('chart-experimental-toggle').check();
  let result=await response;
  for(const [adjustment,label] of [['none','原始'],['qfq','前复权']]){
   for(const [period,periodLabel] of [['daily','日'],['weekly','周'],['monthly','月']]) {
    const button=page.getByRole('button',{name:periodLabel,exact:true});
    const adjButton=page.getByRole('button',{name:label,exact:true});
    if(await adjButton.getAttribute('aria-pressed')!=='true'){
      response=page.waitForResponse(r=>r.url().endsWith('/market/chart')&&r.request().postDataJSON()?.adjustment===adjustment,{timeout:120000});
      await adjButton.click();result=await response;
    }
    if(await button.getAttribute('aria-pressed')!=='true'){
      response=seen.has(`${adjustment}:${period}:2026-10-01:2026-11-06:true`)?Promise.resolve(seen.get(`${adjustment}:${period}:2026-10-01:2026-11-06:true`)):page.waitForResponse(r=>r.url().endsWith('/market/chart')&&r.request().postDataJSON()?.period===period&&r.request().postDataJSON()?.adjustment===adjustment,{timeout:120000});
      await button.click();result=await response;
    }
    const payload=await result.json();
    if(!result.ok()||payload.data?.period!==period||payload.data?.adjustment!==adjustment)throw new Error(JSON.stringify(payload));
    await page.locator('[data-primary-answer]').waitFor({state:'visible',timeout:30000});
    const download=page.waitForEvent('download');
    await page.getByRole('button',{name:'CSV',exact:true}).click();
    const file=await download;const filename=`${name}-${adjustment}-${period}.csv`;await file.saveAs(root+filename);
    const text=await page.locator('body').innerText();
    const entry={name,id,adjustment,period,http_status:result.status(),request:result.request().postDataJSON(),response:payload,export:filename,visible_latest:text.includes(payload.data.latest_price_date),page_errors:errors.slice()};
    report.routes.push(entry);await writeFile(root+'browser-acceptance.json',JSON.stringify(report,null,2));
    console.log(name,adjustment,period,payload.data.bars.length,filename);
   }
  }
  await page.screenshot({path:root+name+'-chart.png',fullPage:true});await page.close();
 }
 const page=await browser.newPage({viewport:{width:1440,height:1080}});
 await page.goto('http://127.0.0.1:15171/instruments/1000001?tab=capital',{waitUntil:'domcontentloaded'});
 await page.getByLabel('开始日期',{exact:true}).fill('2026-10-19');await page.getByLabel('截至日期',{exact:true}).fill('2026-11-06');
 await page.getByRole('checkbox').check();
 const refreshed=page.waitForResponse(r=>r.url().endsWith('/capital/profile')&&r.request().postDataJSON()?.allow_experimental_data===true,{timeout:30000});
 await page.getByRole('button',{name:'刷新资金画像'}).click();
 const capital=await refreshed;const payload=await capital.json();
 await page.getByText('最新观察 · 业务日期窗内现在已知的数据',{exact:true}).waitFor();
 report.capital={status:capital.status(),request:capital.request().postDataJSON(),response:payload,visible_text:await page.locator('body').innerText()};
 await page.screenshot({path:root+'capital.png',fullPage:true});
 report.finished_at=new Date().toISOString();await writeFile(root+'browser-acceptance.json',JSON.stringify(report,null,2));
} finally{await browser.close();}
