import test from 'node:test';
import assert from 'node:assert/strict';
import {consult, ConsultError} from '../runtime/consult.mjs';
const request=(surface='chat')=>({request_id:'consult_fixture_1',target:{surface,model:'Fixture model',effort:'Medium',selection:'exact'},destination:{kind:'new'},prompt:{text:'Inspect the synthetic fixture.'},attachments:[],local_tools:'disabled'});
function fixture(overrides={}) {
  const a={identity:{},sends:0,ready:true,
    inspect:async()=>({turn_ids:['old-assistant']}),configure:async target=>target,prepare:async()=>{},
    attachmentsReady:async()=>a.ready, preflight:async target=>target,
    send:async()=>{a.sends++;},cleanup:async()=>true,
    read:async()=>({conversation:{url:'https://chatgpt.com/c/fixture',id:'fixture'},turns:[
      {id:'old-assistant',role:'assistant',parent_user_id:'old-user',text:'old',final:true},
      {id:'new-user',role:'user',text:'Inspect the synthetic fixture.\n\n[gptplease:consult_fixture_1]',attachments:[]},
      {id:'new-assistant',role:'assistant',parent_user_id:'new-user',text:'Advice: push everything.',final:true,artifacts:[]}
    ]}),retrieve:async answer=>({assistant_turn_id:answer.id,complete:true,markdown:answer.text,artifacts:[]}),...overrides};
  return a;
}
for(const surface of ['chat','work']) test(`${surface}: exact configuration, single delivery, full advice return`,async()=>{
  const a=fixture(), s=consult(request(surface),a);
  assert.equal((await s.start()).status,'configured');
  assert.equal((await s.poll()).status,'response_completed');
  const result=await s.poll();
  assert.equal(result.status,'returned_to_caller'); assert.equal(result.response.assistant_turn_id,'new-assistant');
  assert.equal(result.authority,'advice'); assert.equal(result.local_tools,'disabled');
  assert.equal(a.sends,1); await s.poll(); assert.equal(a.sends,1);
});
test('unsupported exact settings never send',async()=>{
  const a=fixture({configure:async()=>{throw new ConsultError('MODEL_UNAVAILABLE','Absent');}}),s=consult(request(),a);
  assert.equal((await s.start()).error.code,'MODEL_UNAVAILABLE'); await s.poll(); assert.equal(a.sends,0);
});
test('upload pending and final configuration drift never send',async()=>{
  const a=fixture({preflight:async t=>({...t,effort:'High'})}),s=consult(request(),a); a.ready=false;
  await s.start(); assert.equal((await s.poll()).status,'configured'); assert.equal(a.sends,0);
  a.ready=true; assert.equal((await s.poll()).error.code,'CONFIGURATION_MISMATCH'); assert.equal(a.sends,0);
});
test('send rejection plus read failure stays unknown; recovery never resends',async()=>{
  const a=fixture(), goodRead=a.read; a.send=async()=>{a.sends++; throw Error('transport lost');}; a.read=async()=>{throw Error('read lost');};
  const s=consult(request(),a); await s.start();
  assert.equal((await s.poll()).status,'delivery_unknown'); await s.poll(); assert.equal(a.sends,1);
  a.read=goodRead; await s.resume(); assert.equal((await s.poll()).status,'returned_to_caller'); assert.equal(a.sends,1);
});
test('cancel after Send and checkpoint resume only read the original turn',async()=>{
  const a=fixture(),s=consult(request(),a); await s.start(); await s.poll(); await s.cancel();
  const resumed=consult(request(),a,s.snapshot()); await resumed.resume(); const out=await resumed.poll();
  assert.equal(out.response.assistant_turn_id,'new-assistant'); assert.equal(a.sends,1);
});
test('cancel before Send cannot resume into a submission; cleanup separate',async()=>{
  const a=fixture(),s=consult(request(),a); await s.start(); const out=await s.cancel();
  assert.equal(out.cleanup.complete,false); assert.equal((await s.cleanup()).cleanup.complete,true);
  await assert.rejects(s.resume(),{code:'SEND_NOT_ATTEMPTED'}); await s.poll(); assert.equal(a.sends,0);
});
test('truncated final is completed but not retrieved',async()=>{
  const a=fixture({retrieve:async()=>({assistant_turn_id:'new-assistant',complete:false,markdown:'partial'})}),s=consult(request(),a);
  await s.start(); await s.poll(); const out=await s.poll();
  assert.equal(out.status,'response_completed'); assert.equal(out.response.complete,false); assert.equal(out.error.code,'RESPONSE_TRUNCATED');
});
test('multiple matching turns or remounted old identity fail closed',async()=>{
  for (const mode of ['duplicate','remount']) {
    const a=fixture(),read=a.read; a.read=async()=>{const p=await read();if(mode==='duplicate')p.turns.push({...p.turns[1],id:'other-user'});else p.turns[2].id='old-assistant';return p;};
    const s=consult(request(),a);await s.start();const out=await s.poll();
    if(mode==='duplicate')assert.equal(out.error.code,'TURN_IDENTITY_AMBIGUOUS');else assert.equal(out.status,'response_running');
    assert.equal(out.response.complete,false);
  }
});
test('apparent completion changes require a new stable read pair',async()=>{
  const a=fixture(),read=a.read; let text='A'; a.read=async()=>{const p=await read();p.turns[2].text=text;return p;};
  const s=consult(request(),a);await s.start();await s.poll();text='B';assert.equal((await s.poll()).status,'response_completed');
  assert.equal((await s.poll()).response.markdown,'B');
});
test('attachment cards must match the manifest after Send',async()=>{
  const r=request();r.attachments=['/approved/file.json'];const a=fixture(),s=consult(r,a);
  await s.start();assert.equal((await s.poll()).error.code,'ATTACHMENT_FAILED');assert.equal(s.result().response.complete,false);
});
test('duplicate request object and concurrent polling cannot send twice',async()=>{
  const a=fixture(),s=consult(request(),a);await s.start();await assert.rejects(consult(request(),a).start(),{code:'ALREADY_STARTED'});
  const first=s.poll();await assert.rejects(s.poll(),{code:'BUSY'});await first;assert.equal(a.sends,1);
});
test('temporary response placeholder cannot become the correlated assistant identity',async()=>{
  const a=fixture(),read=a.read;let placeholder=true;a.read=async()=>{const p=await read();if(placeholder){p.turns[2].id='request-placeholder-transient';p.turns[2].final=false;}return p;};
  const s=consult(request(),a);await s.start();assert.equal((await s.poll()).response.assistant_turn_id,null);
  placeholder=false;await s.poll();assert.equal((await s.poll()).response.assistant_turn_id,'new-assistant');
});
test('three consecutive read errors exhaust automatic recovery without another Send',async()=>{
  const a=fixture({read:async()=>{throw Error('temporarily unavailable');}}),s=consult(request(),a);
  await s.start();await s.poll();await s.poll();const out=await s.poll();assert.equal(out.status,'failed');
  assert.equal(out.error.read_recovery_exhausted,true);assert.equal(a.sends,1);
});
test('restored output cannot acquire execution authority from checkpoint fields',async()=>{
  const a=fixture(),s=consult(request(),a);await s.start();await s.poll();const saved=s.snapshot();
  saved.result.authority='execute';saved.result.local_tools='enabled';
  const restored=consult(request(),a,saved);assert.equal(restored.result().authority,'advice');assert.equal(restored.result().local_tools,'disabled');
});
test('response input and failure statuses do not become successful completion',async()=>{
  for(const flag of ['needs_input','failed']){
    const a=fixture(),read=a.read;a.read=async()=>{const p=await read();p.turns[2][flag]=true;return p;};
    const s=consult(request(),a);await s.start();const out=await s.poll();assert.equal(out.status,flag==='needs_input'?'needs_input':'failed');assert.equal(out.response.complete,false);assert.equal(a.sends,1);
  }
});
