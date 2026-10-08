import { Cosmograph, type CosmographConfig } from '@cosmograph/cosmograph';
import { tableFromIPC } from 'apache-arrow';

type Context = {graph:string;snapshot:string;projection:string;hierarchy:string|null;layout:string|null;selection:string|null};
type Resource = {uri:string;sha256:string;encoded_bytes:string};
type Manifest = {view_id:string;generation:string;context:Context;points:Resource;links:Resource;counts:{points:string;links:string};decoded_bytes:string};
type Reply = {status:string;session_id:string;revision:string;context:Context;view_id?:string;selection_handle?:string;resources?:Resource[];error?:{message:string}};
const context:Context={graph:'research-graph',snapshot:'fixture-1',projection:'all-v1',hierarchy:'groups-v1',layout:'xy-v1',selection:null};
const budget={max_points:10000,max_links:100000,max_wire_bytes:'33554432',max_decoded_bytes:'134217728',max_scan_edges:'1000000',max_scan_bytes:'268435456',max_working_bytes:'536870912',deadline_ms:60000};
const status=document.querySelector<HTMLDivElement>('#status')!;
const graph=new Cosmograph(document.querySelector<HTMLDivElement>('#graph')!,{enableSimulation:false});
let sid:string|undefined,revision='0',view:Manifest|undefined,selected:string|undefined,generation=0;
const ids:string[]=[];
async function call(op:string,params:Record<string,unknown>):Promise<Reply>{
 const request={cosmolang:'0.1',request_id:crypto.randomUUID(),context:{...context},budget,command:{op,params},...(sid?{session_id:sid,expect_revision:revision}:{})};
 const response=await fetch('/cosmolang',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});
 const result:Reply=await response.json();
 if(result.status!=='ready')throw Error(result.error?.message??result.status);
 sid=result.session_id;revision=result.revision;return result;
}
async function verified(resource:Resource):Promise<ArrayBuffer>{
 const uri=new URL(resource.uri);const response=await fetch(`/objects/${uri.hostname}${uri.pathname}`);if(!response.ok)throw Error(`Artifact HTTP ${response.status}`);
 const bytes=await response.arrayBuffer();
 if(BigInt(bytes.byteLength)!==BigInt(resource.encoded_bytes))throw Error('Artifact length mismatch');
 const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(n=>n.toString(16).padStart(2,'0')).join('');
 if(digest!==resource.sha256)throw Error('Artifact digest mismatch');return bytes;
}
async function install(reply:Reply):Promise<void>{
 const own=++generation;
 const manifest:Manifest=JSON.parse(new TextDecoder().decode(await verified(reply.resources![0])));
 if(BigInt(manifest.counts.points)>BigInt(budget.max_points)||BigInt(manifest.counts.links)>BigInt(budget.max_links)||BigInt(manifest.decoded_bytes)>BigInt(budget.max_decoded_bytes))throw Error('Manifest exceeds browser policy');
 const [pointBytes,linkBytes]=await Promise.all([verified(manifest.points),verified(manifest.links)]);
 if(own!==generation)return;
 const points=tableFromIPC(pointBytes),links=tableFromIPC(linkBytes);
 ids.splice(0,ids.length,...Array.from(points.getChild('id')!,String));
 const config:CosmographConfig={points,links,pointIdBy:'id',linkSourceBy:'source',linkTargetBy:'target',pointXBy:'x',pointYBy:'y',pointLabelBy:'id',enableSimulation:false,onClick:(index?:number)=>{selected=index===undefined?undefined:ids[index];status.textContent=selected??'No selection';}};
 await graph.setConfig(config);
 if(own!==generation)return;
 view=manifest;graph.fitView();status.textContent=`${manifest.counts.points} points, ${manifest.counts.links} quotient links. Select a group to expand.`;
 document.documentElement.dataset.view=manifest.view_id;
 document.documentElement.dataset.points=manifest.counts.points;
}
async function overview():Promise<void>{context.selection=null;await install(await call('view.request',{camera:{mode:'2d',coordinate_frame:'xy-v1',center:[0,0],world_units_per_pixel:1,viewport:{width_px:1200,height_px:800}},frontier_handle:null,columns:[],quality:{membership:'complete',edges:'complete'}}));}
async function follow():Promise<void>{const seed=document.querySelector<HTMLInputElement>('#seed')!.value;const reply=await call('graph.follow',{domain:'projection',seeds:{ids:[{kind:'vertex',id:seed}]},direction:'both',max_hops:2,vertex_predicate:null,edge_predicate:null,quality:{membership:'complete',edges:'complete'}});context.selection=reply.selection_handle!;await install(await call('view.request',{camera:{mode:'2d',coordinate_frame:'xy-v1',center:[0,0],world_units_per_pixel:1,viewport:{width_px:1200,height_px:800}},frontier_handle:null,columns:[],quality:{membership:'complete',edges:'complete'}}));}
async function expand():Promise<void>{if(!view||!selected?.startsWith('h/'))throw Error('Select a collapsed group first');await install(await call('hierarchy.expand',{group:{kind:'aggregate',id:selected},view_id:view.view_id,quality:{membership:'complete',edges:'complete'}}));}
function action(fn:()=>Promise<void>):()=>void{return()=>{status.textContent='Loading…';fn().catch(error=>{status.textContent=String(error);document.documentElement.dataset.error=String(error);});};}
document.querySelector('#overview')!.addEventListener('click',action(overview));
document.querySelector('#follow')!.addEventListener('click',action(follow));
document.querySelector('#expand')!.addEventListener('click',action(expand));
document.querySelector('#fit')!.addEventListener('click',()=>graph.fitView());
// Exposed for the browser qualification harness; production UI uses point clicks.
Object.assign(window,{cosmolang:{expandGroup:async(id:string)=>{selected=id;await expand();},graph}});
await call('session.open',{renderer:'cosmograph',dimensions:2});await overview();
