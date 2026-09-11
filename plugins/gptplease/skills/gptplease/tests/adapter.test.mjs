import test from 'node:test';
import assert from 'node:assert/strict';
import {consult} from '../runtime/consult.mjs';
import {ChatAdapter, WorkAdapter} from '../runtime/cua-chatgpt.mjs';

const target = surface => ({surface, model:'Fixture model', effort:'Medium', selection:'exact'});
const url='https://chatgpt.com/c/review-fixture';

for (const Adapter of [ChatAdapter,WorkAdapter]) test(`${Adapter.name}: zero-file manifest rejects an unrelated attachment at preflight`,async()=>{
  const tab={url:async()=>url,playwright:{locator:()=>({press:async()=>{}})}};
  const adapter=new Adapter(tab);
  adapter.expectedURL=url;
  adapter.read=async()=>({turns:[]});
  adapter.composer=async()=>({text:'authorized prompt',attachments:['private-unapproved.pdf']});
  adapter.assertSurface=async()=>{};
  adapter.openPicker=async()=>{};
  adapter.settings=async()=>({model:['Fixture model'],effort:'Medium'});
  adapter.attachmentState=async()=>({names:['private-unapproved.pdf'],pending:false,errors:[]});
  await assert.rejects(adapter.preflight(target(adapter.surface),'authorized prompt',[],{kind:'existing',url},[]),{code:'ATTACHMENT_FAILED'});
});

test('production retrieve rejects operator/braces-stripped code',async()=>{
  let clipboard='';
  const corrupt='if count 0 return false';
  const answer={id:'assistant-review',text:'if (count <= 0) {\n  return false;\n}',final:true,artifacts:[]};
  const section={filter(){return this;},getByTestId:()=>({click:async()=>{clipboard=corrupt;}})};
  const tab={playwright:{locator:()=>section},clipboard:{read:async()=>[],writeText:async text=>{clipboard=text;},readText:async()=>clipboard}};
  const adapter=new ChatAdapter(tab);
  adapter.read=async()=>({turns:[answer]});
  const returned=await adapter.retrieve(answer);
  assert.equal(returned.complete,false);
  assert.equal(returned.markdown,null);
});

test('checkpoint restored to a fresh adapter reserves its request identity',async()=>{
  const request={request_id:'independent_review_1',target:target('chat'),destination:{kind:'existing',url},prompt:{text:'Review fixture'},attachments:[],local_tools:'disabled'};
  const text=`${request.prompt.text}\n\n[gptplease:${request.request_id}]`;
  let sends=0;
  const turns=[];
  const fixture=()=>({identity:{},inspect:async()=>({turn_ids:turns.map(t=>t.id)}),configure:async t=>t,prepare:async()=>{},attachmentsReady:async()=>true,preflight:async t=>t,send:async()=>{sends++;turns.push({id:`u${sends}`,role:'user',text,attachments:[]},{id:`a${sends}`,role:'assistant',parent_user_id:`u${sends}`,text:'Full answer',final:true,artifacts:[]});},read:async()=>({conversation:{id:'review-fixture',url},turns}),retrieve:async a=>({assistant_turn_id:a.id,markdown:a.text,complete:true})});
  const original=consult(request,fixture());
  await original.start();await original.poll();
  const restoredAdapter=fixture();
  const restored=consult(request,restoredAdapter,original.snapshot());
  await restored.resume();await restored.poll();
  const duplicate=consult(request,restoredAdapter);
  await assert.rejects(duplicate.start(),{code:"ALREADY_STARTED"});
  assert.equal(sends,1);
  assert.equal(turns.filter(t=>t.role==='user' && t.text===text).length,1);
});

test('generated file buttons retain sandbox links and explicit unread-byte state',async()=>{
  let clipboard='';
  const answer={id:'assistant-file',text:'transport-artifact.txt\nDone.',final:true,artifacts:[{kind:'file',id:'file-45',label:'transport-artifact.txt',url:null,bytes_retrieved:false}]};
  const section={filter(){return this;},getByTestId:()=>({click:async()=>{clipboard='[](sandbox:/workspace/transport-artifact.txt)\nDone.';}})};
  const tab={playwright:{locator:()=>section},clipboard:{read:async()=>[],writeText:async text=>{clipboard=text;},readText:async()=>clipboard}};
  const adapter=new ChatAdapter(tab);adapter.read=async()=>({turns:[answer]});
  const out=await adapter.retrieve(answer);
  assert.equal(out.complete,true);assert.equal(out.artifacts.length,1);
  assert.equal(out.artifacts[0].url,'sandbox:/workspace/transport-artifact.txt');assert.equal(out.artifacts[0].bytes_retrieved,false);
  assert.match(out.markdown,/^\[transport-artifact\.txt\]/);assert.equal(clipboard,'');
});

test('surface-incompatible top tiers fail before browser actions',async()=>{
  await assert.rejects(new WorkAdapter({}).configure({surface:'work',effort:'Pro'}),{code:'EFFORT_UNAVAILABLE'});
  await assert.rejects(new ChatAdapter({}).configure({surface:'chat',effort:'Ultra'}),{code:'EFFORT_UNAVAILABLE'});
});
