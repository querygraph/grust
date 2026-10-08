import {chromium} from '@playwright/test';
import {writeFile,mkdir} from 'node:fs/promises';
const output=process.argv[2];await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1400,height:1000}});
const errors=[];const consoleMessages=[];page.on('pageerror',e=>errors.push(String(e)));page.on('console',m=>consoleMessages.push({type:m.type(),text:m.text()}));
const results=[];
try{
 await page.goto('http://127.0.0.1:18766');
 await page.waitForFunction(()=>document.documentElement.dataset.points==='3',{timeout:90000});results.push({control:'overview_three_groups',outcome:'passed'});
 await page.evaluate(()=>window.cosmolang.expandGroup('h/a'));
 await page.waitForFunction(()=>document.documentElement.dataset.points==='4');results.push({control:'expand_group_browser_update',outcome:'passed'});
 await page.screenshot({path:output+'/expanded.png'});
 await page.locator('#follow').click();
 await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('2 points'),{timeout:60000});results.push({control:'follow_exact_two_hops',outcome:'passed'});
 await page.screenshot({path:output+'/follow.png'});
 const canvas=await page.locator('canvas').count();if(canvas<1)throw Error('Cosmograph canvas missing');results.push({control:'real_cosmograph_canvas',outcome:'passed',count:canvas});
 const status=await page.locator('#status').innerText();await writeFile(output+'/browser.json',JSON.stringify({observed_utc:new Date().toISOString(),sdk:'@cosmograph/cosmograph@2.5.1',browser:await browser.version(),results,errors,consoleMessages,status},null,2));
 if(errors.length)throw Error(errors.join('\n'));
}catch(error){await writeFile(output+'/browser-failed.json',JSON.stringify({observed_utc:new Date().toISOString(),results,errors,consoleMessages,error:String(error),status:await page.locator('#status').innerText()},null,2));throw error;}finally{await browser.close();}
