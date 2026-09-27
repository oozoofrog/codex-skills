#!/usr/bin/env python3
"""Small stdio MCP client: discover live tools, bounded inspect, image capture and reviewed code.
No server installation, global config edits or automatic mutation retries.
"""
from __future__ import annotations
import argparse
import base64
import json
from pathlib import Path
import queue
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from workflow import read, write_new, fingerprint, file_hash, check_plan, predecision_gate

LIMIT=8*1024*1024
class Client:
    def __init__(self, command, log, timeout=30):
        if not isinstance(command,list) or not command or any(not isinstance(v,str) for v in command):
            raise ValueError('config command must be an argv array')
        self.timeout=timeout;self.id=0;self.messages=queue.Queue(maxsize=64)
        self.log=log.open('xb')
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,start_new_session=True)
        def consume():
            try:
                while True:
                    line=self.process.stdout.readline(LIMIT+1)
                    if not line: self.messages.put(None,timeout=1);return
                    if len(line)>LIMIT:raise ValueError('MCP message exceeds 8 MiB')
                    self.messages.put(json.loads(line),timeout=1)
            except Exception as exc:
                try:self.messages.put(exc,timeout=1)
                except queue.Full:pass
        threading.Thread(target=consume,daemon=True).start()
    def send(self,message):
        data=json.dumps(message).encode()+b'\n'
        if len(data)>LIMIT:raise ValueError('outgoing MCP message exceeds 8 MiB')
        done=queue.Queue(maxsize=1)
        def write():
            try:self.process.stdin.write(data);self.process.stdin.flush();done.put(None)
            except Exception as exc:done.put(exc)
        threading.Thread(target=write,daemon=True).start()
        try:error=done.get(timeout=self.timeout)
        except queue.Empty:raise TimeoutError('MCP write deadline; outcome may be unknown')
        if error:raise OSError('MCP pipe write failed') from error
    def request(self,method,params):
        self.id+=1;ident=self.id
        deadline=time.monotonic()+self.timeout
        self.send({'jsonrpc':'2.0','id':ident,'method':method,'params':params})
        while True:
            left=deadline-time.monotonic()
            if left<=0:raise TimeoutError('MCP deadline; inspect before retrying a mutation')
            try:message=self.messages.get(timeout=left)
            except queue.Empty:raise TimeoutError('MCP deadline; outcome may be unknown')
            if message is None:raise ValueError('MCP process ended')
            if isinstance(message,Exception):raise ValueError('invalid MCP stream') from message
            if 'method' in message:
                if 'id' in message:self.send({'jsonrpc':'2.0','id':message['id'],'error':{'code':-32601,'message':'client requests unsupported'}})
                continue
            if message.get('id')!=ident:raise ValueError('unexpected MCP response id')
            if 'error' in message:raise ValueError('MCP protocol error: '+str(message['error'].get('code')))
            return message['result']
    def discover(self):
        hello=self.request('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'jev-blender-use','version':'0.2.1'}})
        self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
        tools=[];cursor=None
        for _ in range(20):
            page=self.request('tools/list',{'cursor':cursor} if cursor else {})
            tools.extend(page.get('tools',[]));cursor=page.get('nextCursor')
            if not cursor:break
        else:raise ValueError('excessive tool pagination')
        return hello,tools
    def close(self):
        if self.process.poll() is None:
            if os.name=="posix":os.killpg(self.process.pid,signal.SIGTERM)
            else:self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                if os.name=="posix":os.killpg(self.process.pid,signal.SIGKILL)
                else:self.process.kill()
                self.process.wait()
        self.process.stdin.close();self.process.stdout.close();self.log.close()

def binding(tools, names):
    found=[t for t in tools if t.get('name') in names]
    if len(found)!=1:raise ValueError('missing or ambiguous capability: '+','.join(names))
    return found[0]

def call(client,tool,args):
    schema=tool.get('inputSchema',{})
    if set(schema.get('required',[]))-set(args):raise ValueError('tool schema needs additional arguments')
    result=client.request('tools/call',{'name':tool['name'],'arguments':args})
    if result.get('isError'):raise ValueError('MCP tool reported an error')
    return result

def execution_args(tool,code):
    props=tool.get('inputSchema',{}).get('properties',{})
    if 'code' not in props:raise ValueError('execution tool does not expose code argument')
    args={'code':code}
    if 'user_prompt' in props:args['user_prompt']='Inspect or execute the reviewed Blender task with explicit scope.'
    return args

def extract(result, expected_nonce=None):
    candidates=[result.get('structuredContent')]
    for c in result.get('content',[]):
        if c.get('type')=='text':
            text=c.get('text','')
            try:candidates.append(json.loads(text))
            except ValueError:pass
            # Community may nest printed stdout within JSON result text.
            candidates.append(text)
    def visit(v,depth=0):
        if depth>6:return None
        if isinstance(v,dict):
            if v.get('schema_version')==1 and 'objects' in v:
                if expected_nonce is not None and v.get('_receipt_nonce')!=expected_nonce:return None
                return {k:value for k,value in v.items() if k!='_receipt_nonce'}
            if v.get('status')=='error':raise ValueError('Blender execution reported error')
            for key in ('result','output','text'):
                r=visit(v.get(key),depth+1)
                if r is not None:return r
        if isinstance(v,str):
            for line in reversed(v.splitlines()):
                if line.startswith('CODEX_BLENDER_JSON:'):
                    parsed=json.loads(line[len('CODEX_BLENDER_JSON:'):]);found=visit(parsed,depth+1)
                    if found is not None:return found
            try:return visit(json.loads(v),depth+1)
            except (ValueError,TypeError):pass
        return None
    for c in candidates:
        value=visit(c)
        if value is not None:return value
    raise ValueError('no structured Blender evidence in tool response')

def inspection_code(objects,limit=50):
    # Same inspector for CLI/live MCP, transferred as reviewed code; no bridge filesystem assumptions.
    source=Path(__file__).with_name('scene_state.py').read_text()
    return "import json\n_namespace={'__name__':'codex_scene_state'}\nexec(compile("+repr(source)+",'<codex-scene-state>','exec'),_namespace)\nresult=_namespace['inspect_scene'](objects="+repr(objects)+",limit="+repr(limit)+")\nprint('CODEX_BLENDER_JSON:'+json.dumps(result))\n"

def execute_code(plan,script,before,checkpoint,candidate,nonce):
    check_plan(plan)
    if not checkpoint or not Path(checkpoint).is_absolute():raise ValueError('interactive code requires explicit absolute new checkpoint .blend')
    scope=list(dict.fromkeys(plan['target_objects']+plan.get('protected_objects',[])))
    # Compare before state in the same main-thread command before mutation.
    code=inspection_code(scope,100).replace("print('CODEX_BLENDER_JSON:'+json.dumps(result))", "")
    code+="\nimport hashlib, os, bpy\n_actual=hashlib.sha256(json.dumps(result,ensure_ascii=False,sort_keys=True,allow_nan=False).encode('utf-8')).hexdigest()\n"
    code+=f"if _actual != {fingerprint(before)!r}: raise RuntimeError('Live scene changed; inspect again')\n"
    code+=f"if os.path.lexists({checkpoint!r}): raise RuntimeError('Checkpoint already exists')\n"
    code+=f"_save=bpy.ops.wm.save_as_mainfile(filepath={checkpoint!r},copy=True,check_existing=False)\n"
    code+="if 'FINISHED' not in _save: raise RuntimeError('Checkpoint failed')\n"
    code+="exec(compile("+repr(script)+",'<reviewed-user-script>','exec'),{'__name__':'__main__'})\n"
    code+=inspection_code(scope,100).replace("print('CODEX_BLENDER_JSON:'+json.dumps(result))", "")
    code+=f"if os.path.lexists({candidate!r}): raise RuntimeError('Candidate already exists')\n"
    code+=f"_save=bpy.ops.wm.save_as_mainfile(filepath={candidate!r},copy=True,check_existing=False)\n"
    code+="if 'FINISHED' not in _save: raise RuntimeError('Candidate copy save failed')\n"
    code+=f"result['_receipt_nonce']={nonce!r}\n"
    code+="print('CODEX_BLENDER_JSON:'+json.dumps(result))\n"
    return code

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['discover','inspect','capture','execute'])
    p.add_argument('--config',required=True,help='Trusted JSON with command argv for installed stdio server')
    p.add_argument('--output-dir',required=True);p.add_argument('--objects',nargs='*');p.add_argument('--timeout',type=float,default=30)
    p.add_argument('--run-dir',help='Bind capture to a previous live MCP candidate');p.add_argument('--pre-decision');p.add_argument('--script');p.add_argument('--plan',help='Plan for execute or scope-matched inspect');p.add_argument('--before');p.add_argument('--checkpoint');p.add_argument('--trusted-script',action='store_true')
    a=p.parse_args();client=None;mutation_submitted=False;result={'status':'failed','transport':'mcp'}
    try:
        if not 0<a.timeout<=600:raise ValueError('timeout must be 0..600 seconds')
        out=Path(a.output_dir).resolve();out.mkdir(parents=True,exist_ok=False)
        if a.operation=='inspect' and a.plan and a.objects is not None:
            raise ValueError('inspect accepts --plan or --objects, not both')
        inspect_plan=check_plan(read(a.plan)) if a.operation=='inspect' and a.plan else None
        config=read(a.config);client=Client(config['command'],out/'server.log',a.timeout)
        hello,tools=client.discover();write_new(out/'tools.json',{'server':hello,'tools':tools})
        if a.operation=='discover':result={'status':'completed','transport':'mcp','server':hello,'tool_names':[t['name'] for t in tools],'scene_connection':'not_probed'}
        elif a.operation=='capture':
            tool=binding(tools,['get_screenshot_of_area_as_image','get_viewport_screenshot'])
            props=tool.get('inputSchema',{}).get('properties',{})
            args={k:v for k,v in {'area_ui_type':'VIEW_3D','size_limit_in_bytes':2000000,'max_size':1000,'user_prompt':'Capture current viewport for observation.'}.items() if k in props}
            capture_run=Path(a.run_dir).resolve() if a.run_dir else None
            expected_state=None
            if capture_run:
                capture_result=read(capture_run/'result.json');capture_plan=read(capture_run/'plan.json')
                expected_state=read(capture_run/'after.json')
                if capture_result.get('transport')!='mcp' or capture_result.get('status')!='staged':raise ValueError('capture needs staged MCP candidate')
                if file_hash(capture_run/'candidate.blend')!=capture_result.get('candidate_sha256') or file_hash(capture_run/'after.json')!=capture_result.get('after_sha256'):
                    raise ValueError('capture candidate/evidence changed')
                inspect_tool=binding(tools,['execute_blender_code'])
                inspect_code=inspection_code(list(dict.fromkeys(capture_plan['target_objects']+capture_plan.get('protected_objects',[]))),100)
                fresh=extract(call(client,inspect_tool,execution_args(inspect_tool,inspect_code)))
                if fingerprint(fresh)!=fingerprint(expected_state):raise ValueError('live state changed since candidate')
            raw=call(client,tool,args);images=[]
            for c in raw.get('content',[]):
                if c.get('type')!='image':continue
                suffix={'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp'}.get(c.get('mimeType'))
                if suffix is None:raise ValueError('unsupported image type')
                path=out/f'viewport-{len(images)}{suffix}';path.write_bytes(base64.b64decode(c['data'],validate=True))
                images.append({'path':str(path),'sha256':file_hash(path)})
            if not images:raise ValueError('tool returned no image blocks')
            if capture_run:
                fresh=extract(call(client,inspect_tool,execution_args(inspect_tool,inspect_code)))
                if fingerprint(fresh)!=fingerprint(expected_state):raise ValueError('live state changed during capture')
                for i,item in enumerate(images):
                    receipt=out/f'capture-{i}.json'
                    write_new(receipt,{'source_sha256':capture_result['candidate_sha256'],'preview_sha256':item['sha256'],
                        'kind':'viewport','scene_sha256':fingerprint(fresh),'frame':fresh['scene'].get('frame')})
                    item['render_metadata']=str(receipt)
            result={'status':'completed','transport':'mcp','images':images,'visual_review':'not_performed','scene_binding':'capture is live; record same-frame inspect separately'}
        else:
            tool=binding(tools,['execute_blender_code'])
            if a.operation=='execute':
                if not a.trusted_script or not all((a.script,a.plan,a.before,a.checkpoint)):raise ValueError('execute needs trusted-script, plan, before, and checkpoint')
                plan=read(a.plan);before=read(a.before)
                # Shared deterministic risk guard is also used for live mutation.
                from scene_guard import guard
                blockers=guard(plan,before)
                if blockers:raise ValueError('preflight refused: '+','.join(blockers))
                predecision=read(a.pre_decision) if a.pre_decision else None
                predecision_gate(plan,before,predecision)
                script=Path(a.script).read_text()
                write_new(out/'plan.json',plan);write_new(out/'before.json',before)
                (out/'script.py').write_text(script)
                if predecision:write_new(out/'pre-decision.json',predecision)
                nonce=uuid.uuid4().hex
                code=execute_code(plan,script,before,a.checkpoint,str(out/'candidate.blend'),nonce)
            else:
                scope=list(dict.fromkeys(inspect_plan['target_objects']+inspect_plan.get('protected_objects',[]))) if inspect_plan else a.objects
                code=inspection_code(scope,100)
            mutation_submitted=a.operation=='execute'
            raw=call(client,tool,execution_args(tool,code));state=extract(raw,nonce if a.operation=='execute' else None);write_new(out/'state.json',state)
            result={'status':'completed','transport':'mcp','state':str(out/'state.json'),'state_sha256':fingerprint(state),'visual_review':'not_performed'}
            if a.operation=='execute':
                from scene_worker import protected_changed
                changes=protected_changed(plan,before,state)
                write_new(out/'after.json',state)
                result.update(status='needs_review' if changes else 'staged',protected_changes=changes,
                    candidate_sha256=file_hash(out/'candidate.blend'),plan_sha256=file_hash(out/'plan.json'),
                    before_sha256=file_hash(out/'before.json'),after_sha256=file_hash(out/'after.json'),
                    script_sha256=file_hash(out/'script.py'),checkpoint_sha256=file_hash(a.checkpoint),
                    checkpoint=a.checkpoint,predecision_origin=predecision.get('origin') if predecision else 'codex_plan_and_exact_guard')
                write_new(out/'trace.json',{'operation':'execute','transport':'mcp','tool':tool['name'],
                    'protected_changes':changes,'outcome':result['status'],'checkpoint':a.checkpoint})
        write_new(out/'result.json',result)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (OSError,ValueError,TypeError,KeyError,TimeoutError) as exc:
        result.update(reason=str(exc),outcome='unknown_reinspect' if mutation_submitted else 'not_modified')
        if 'out' in locals() and out.exists() and not (out/'result.json').exists():write_new(out/'result.json',result)
        print(json.dumps(result));return 2
    finally:
        if client:client.close()
if __name__=='__main__':sys.exit(main())
