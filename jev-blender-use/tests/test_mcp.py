import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from mcp_bridge import Client, binding, extract, execution_args, execute_code

class MCPTests(unittest.TestCase):
    def test_official_and_community_envelopes(self):
        state={'schema_version':1,'objects':{},'scene':{}}
        for value in [ {'structuredContent':{'status':'ok','result':state}},
                       {'content':[{'type':'text','text':json.dumps({'result':{'output':'CODEX_BLENDER_JSON:'+json.dumps(state)}})}]} ]:
            self.assertEqual(extract(value),state)
        with self.assertRaises(ValueError):extract({'content':[{'type':'text','text':'Success!'}]})
    def test_execution_receipt_ignores_earlier_debug_marker(self):
        old={'schema_version':1,'objects':{'Head':{'hide_render':False}}}
        final={'schema_version':1,'objects':{'Head':{'hide_render':True}},'_receipt_nonce':'run-123'}
        output='CODEX_BLENDER_JSON:'+json.dumps(old)+'\nCODEX_BLENDER_JSON:'+json.dumps(final)
        result={'content':[{'type':'text','text':json.dumps({'result':{'output':output}})}]}
        self.assertTrue(extract(result,'run-123')['objects']['Head']['hide_render'])
        with self.assertRaises(ValueError):extract(result,'other-run')
    def test_schema_required_arguments(self):
        tool={'name':'execute_blender_code','inputSchema':{'properties':{'code':{},'user_prompt':{}},'required':['code','user_prompt']}}
        self.assertEqual(set(execution_args(tool,'print(1)')),{'code','user_prompt'})
        with self.assertRaises(ValueError):binding([tool,tool],['execute_blender_code'])
    def test_stdio_protocol(self):
        script='''import sys,json
for line in sys.stdin:
 m=json.loads(line)
 if 'id' not in m: continue
 method=m['method']
 result={'protocolVersion':'2024-11-05','capabilities':{},'serverInfo':{'name':'fixture','version':'1'}} if method=='initialize' else {'tools':[{'name':'execute_blender_code','inputSchema':{'type':'object','properties':{'code':{}},'required':['code']}}]} if method=='tools/list' else {'structuredContent':{'status':'ok','result':{'schema_version':1,'objects':{},'scene':{}}}}
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
'''
        with tempfile.TemporaryDirectory() as d:
            c=Client([sys.executable,'-u','-c',script],Path(d)/'stderr',1)
            try:
                hello,tools=c.discover();self.assertEqual(hello['serverInfo']['name'],'fixture');self.assertEqual(len(tools),1)
                r=c.request('tools/call',{'name':tools[0]['name'],'arguments':{'code':'pass'}})
                self.assertEqual(extract(r)['objects'],{})
            finally:c.close()
    def test_stalled_write_has_deadline(self):
        with tempfile.TemporaryDirectory() as d:
            c=Client([sys.executable,'-c','import time; time.sleep(10)'],Path(d)/'stderr',.05)
            start=time.monotonic()
            try:
                with self.assertRaises(TimeoutError):c.request('tools/call',{'code':'x'*1000000})
                self.assertLess(time.monotonic()-start,.8)
            finally:c.close()
    def test_execution_single_final_evidence_marker_and_snapshot(self):
        plan={'schema_version':1,'task_id':'x','goal':'x','target_objects':['Body'],'protected_objects':[],
              'operations':[{'type':'set_material','target':'Body'}],'validation':[{'kind':'exists','object':'Body'}],'visual_requirements':[]}
        code=execute_code(plan,'pass',{'objects':{}},'/tmp/new-checkpoint.blend','/tmp/new-candidate.blend','nonce1')
        self.assertEqual(code.count("print('CODEX_BLENDER_JSON:'"),1)
        self.assertIn('Live scene changed',code);self.assertIn('Candidate copy save failed',code)
        compile(code,'probe','exec')
if __name__=='__main__':unittest.main()
