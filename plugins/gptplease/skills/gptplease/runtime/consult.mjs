/** Session-scoped consultation transport. No browser creation, provider, or local tools. */
export class ConsultError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}
export const fail = (code, message) => { throw new ConsultError(code, message); };
const used = new WeakMap();
const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const copy = value => structuredClone(value);
const names = paths => paths.map(p => p.split('/').pop()).sort();
const terminal = new Set(['returned_to_caller', 'failed', 'needs_input', 'cancelled']);

export function validateRequest(r) {
  if (!r || !/^[a-zA-Z0-9_-]{8,100}$/.test(r.request_id ?? '') ||
      !['chat', 'work'].includes(r.target?.surface) || typeof r.target.model!=='string' || !r.target.model.trim() || typeof r.target.effort!=='string' || !r.target.effort.trim() ||
      r.target.selection !== 'exact' || r.local_tools !== 'disabled' || typeof r.prompt?.text!=='string' || !r.prompt.text.trim() ||
      !['new', 'existing'].includes(r.destination?.kind)) fail('INVALID_REQUEST', 'Resolve policy into an exact execution contract first.');
  if (r.destination.kind === 'existing' && !/^https:\/\/chatgpt\.com\/c\/[a-zA-Z0-9-]+$/.test(r.destination.url ?? ''))
    fail('INVALID_REQUEST', 'Existing destination requires its exact conversation URL.');
  if (!Array.isArray(r.attachments) || r.attachments.some(p => typeof p !== 'string' || !p.startsWith('/') || !p.split('/').pop()) ||
      new Set(names(r.attachments)).size !== r.attachments.length) fail('INVALID_REQUEST', 'Use unique filenames and exact authorized absolute paths.');
}

export function consult(request, adapter, checkpoint) {
  validateRequest(request);
  const r = copy(request);
  const marker = `[gptplease:${r.request_id}]`;
  const submitted = `${r.prompt.text}\n\n${marker}`;
  let result = {request_id:r.request_id, status:'prepared', requested:copy(r.target), observed:null,
    conversation:null, delivery:{attempted:false, confirmed:false, user_turn_id:null},
    response:{assistant_turn_id:null, complete:false, markdown:null, artifacts:[]},
    attachments:r.attachments.map(path => ({path, name:path.split('/').pop(), confirmed:false})),
    authority:'advice', local_tools:'disabled', warnings:[], history:['prepared'], error:null,
    cleanup:{attempted:false, complete:false}};
  let baseline = [], busy = false, cancelled = false, previousFinal = null, readErrors = 0;
  const mark = status => { if (result.status !== status) {result.status=status; result.history.push(status);} };
  const warning = message => {if (!result.warnings.includes(message)) result.warnings.push(message);};
  const snapshot = () => copy({version:1, request:r, submitted, baseline, result});
  const value = () => copy(result);
  function error(e, fallback) {
    result.error={code:e.code ?? fallback, message:String(e.message ?? e), retryable_read:result.delivery.attempted,
      automatic_new_submission:false};
  }
  function checkCancelled() {if (cancelled) fail('CANCELLED','Caller cancelled.');}
  async function exclusive(fn) {
    if (busy) fail('BUSY','Wait for the current operation; concurrent browser mutations are not allowed.');
    busy=true;
    try {return await fn();} finally {busy=false;}
  }
  if (checkpoint) {
    if (checkpoint.version !== 1 || !equal(checkpoint.request,r) || checkpoint.submitted !== submitted ||
        !checkpoint.result.delivery.attempted) fail('INVALID_CHECKPOINT','Only a matching attempted submission may resume as read-only.');
    let requests=used.get(adapter.identity);
    if(!requests){requests=new Set();used.set(adapter.identity,requests);}
    requests.add(r.request_id);
    result=copy(checkpoint.result); baseline=copy(checkpoint.baseline);
    result.request_id=r.request_id;result.requested=copy(r.target);result.authority='advice';result.local_tools='disabled';
    result.response.complete=false; mark(result.delivery.confirmed?'response_running':'delivery_unknown');
  }
  async function observe() {
    const page = await adapter.read(result.conversation);
    checkCancelled();
    if (result.conversation && page.conversation?.id !== result.conversation.id)
      fail('TURN_IDENTITY_AMBIGUOUS','The browser left the known conversation.');
    if (!page.conversation?.id) return value();
    if (r.destination.kind === 'existing' && page.conversation.url !== r.destination.url)
      fail('TURN_IDENTITY_AMBIGUOUS','Existing destination changed.');
    const users = page.turns.filter(t => t.role === 'user' && t.text === submitted && !baseline.includes(t.id));
    if (users.length > 1) fail('TURN_IDENTITY_AMBIGUOUS','Multiple matching user turns.');
    if (!users.length) return value();
    const user=users[0];
    if (!user.id || (result.delivery.user_turn_id && result.delivery.user_turn_id !== user.id))
      fail('TURN_IDENTITY_AMBIGUOUS','User identity changed.');
    result.conversation=copy(page.conversation);
    const firstConfirmation=!result.delivery.confirmed;
    result.delivery.confirmed=true; result.delivery.user_turn_id=user.id;
    if (!equal([...user.attachments].sort(), names(r.attachments))) fail('ATTACHMENT_FAILED','Received user attachments do not match the authorized manifest.');
    result.attachments.forEach(a => a.confirmed=true);
    if(firstConfirmation)mark('delivery_confirmed');
    const replies=page.turns.filter(t => t.role === 'assistant' && t.parent_user_id === user.id && !baseline.includes(t.id));
    if (replies.length > 1) fail('TURN_IDENTITY_AMBIGUOUS','Multiple candidate assistant turns.');
    const answer=replies[0];
    if (!answer || answer.id?.startsWith('request-placeholder-')) {mark('response_running'); return value();}
    if (!answer.id || (result.response.assistant_turn_id && result.response.assistant_turn_id !== answer.id))
      fail('TURN_IDENTITY_AMBIGUOUS','Assistant identity changed.');
    result.response.assistant_turn_id=answer.id;
    if (answer.needs_input) {mark('needs_input'); error(new ConsultError('RESPONSE_NEEDS_INPUT',answer.text),'RESPONSE_NEEDS_INPUT'); return value();}
    if (answer.failed) fail('RESPONSE_FAILED',answer.text || 'The response failed.');
    if (!answer.final) {previousFinal=null; mark('response_running'); return value();}
    mark('response_completed');
    // Two distinct reads must agree after a final-answer control appears. Streaming absence alone is insufficient.
    const signature=JSON.stringify([answer.id,answer.text,answer.code_blocks,answer.artifacts]);
    if (signature !== previousFinal) {previousFinal=signature; return value();}
    const response=await adapter.retrieve(answer);
    checkCancelled();
    if (response.assistant_turn_id !== answer.id || !response.complete || typeof response.markdown !== 'string' || !response.markdown.trim()) {
      error(new ConsultError('RESPONSE_TRUNCATED','Final answer exists, but full retrieval is unverified.'),'RESPONSE_TRUNCATED'); return value();
    }
    result.response={...response, artifacts:response.artifacts ?? []};
    result.error=null; mark('response_retrieved'); mark('returned_to_caller');
    return value();
  }
  async function readSafely() {
    try {const observed=await observe();readErrors=0;return observed;} catch(e) {
      if (cancelled) {mark('cancelled'); error(e,'CANCELLED');}
      else if (['TURN_IDENTITY_AMBIGUOUS','ATTACHMENT_FAILED','RESPONSE_FAILED'].includes(e.code)) {mark('failed'); error(e,e.code);}
      else {error(e,'UI_DRIFT'); warning('Read failed; recover only by reading the same submission.');
        if(++readErrors>=3){mark('failed');result.error.read_recovery_exhausted=true;}
      }
      return value();
    }
  }
  return {
    snapshot, result:value,
    start:() => exclusive(async () => {
      if (result.status !== 'prepared') fail('ALREADY_STARTED','This consultation cannot start again.');
      let requests=used.get(adapter.identity);
      if (!requests) {requests=new Set(); used.set(adapter.identity,requests);}
      if (requests.has(r.request_id)) fail('ALREADY_STARTED','This request ID has already been used in this browser session.');
      requests.add(r.request_id);
      try {
        const initial=await adapter.inspect(r.destination);
        baseline=initial.turn_ids;
        checkCancelled();
        result.observed=await adapter.configure(r.target);
        if (!equal(result.observed,r.target)) fail('CONFIGURATION_MISMATCH','Actual settings differ from requested settings.');
        checkCancelled(); mark('configured');
        await adapter.prepare(submitted,r.attachments);
        checkCancelled();
      } catch(e) {mark(cancelled?'cancelled':'failed'); error(e,'UI_DRIFT');}
      return value();
    }),
    poll:() => exclusive(async () => {
      if (terminal.has(result.status)) return value();
      if (result.status === 'prepared') fail('SEND_NOT_ATTEMPTED','Call start first.');
      if (!result.delivery.attempted) {
        try {
          checkCancelled();
          if (!await adapter.attachmentsReady(r.attachments)) return value();
          mark('attachments_ready');
          const observed=await adapter.preflight(r.target,submitted,r.attachments,r.destination,baseline);
          if (!equal(observed,r.target)) fail('CONFIGURATION_MISMATCH','Final settings changed.');
          result.observed=observed; checkCancelled();
          result.delivery.attempted=true; mark('send_attempted');
          try {await adapter.send();} catch(e) {error(e,'DELIVERY_UNKNOWN');}
          mark('delivery_unknown');
        } catch(e) {mark(cancelled?'cancelled':'failed'); error(e,'UI_DRIFT'); return value();}
      }
      return readSafely();
    }),
    cancel:async () => {
      if(result.status==='returned_to_caller')return value();
      cancelled=true; result.response.complete=false; mark('cancelled');
      error(new ConsultError('CANCELLED',result.delivery.attempted?'Submission may already exist; retain its identity.':'Cancelled before Send.'),'CANCELLED');
      // Cleanup is explicit and separate; never race an in-flight upload/configuration.
      return value();
    },
    cleanup:() => exclusive(async () => {
      if (!cancelled || result.delivery.attempted) return value();
      result.cleanup.attempted=true;
      try {result.cleanup.complete=await adapter.cleanup(submitted,r.attachments);} catch(e) {warning(`Cleanup incomplete: ${e.message}`);}
      return value();
    }),
    resume:() => exclusive(async () => {
      if (!result.delivery.attempted) fail('SEND_NOT_ATTEMPTED','A cancelled unsent request cannot resume into Send.');
      if (result.status === 'returned_to_caller') return value();
      cancelled=false; readErrors=0; mark(result.delivery.confirmed?'response_running':'delivery_unknown');
      return readSafely();
    })
  };
}
