import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from workflow import validate, check_plan, completion, evidence_state, fingerprint, file_hash, finalize
from decision import prepare, judge
from benchmark import retry, record
from jev_select import ABSTAIN


def plan():
    return {'schema_version':1,'task_id':'mesh','goal':'reduce mesh','target_objects':['Body'],'protected_objects':['Head'],
            'operations':[{'type':'modifier','target':'Body'}],
            'validation':[{'kind':'polygon_reduction','object':'Body','minimum':.3}], 'visual_requirements':[]}
def scene(n=100):
    def obj(count):return {'type':'MESH','mesh':{'polygons':count,'sha256':'fixed'},'evaluated_mesh':{'polygons':count},'transform':[1]*16,'material_sha256':'m','modifier_sha256':'d'}
    return {'schema_version':1,'objects':{'Body':obj(n),'Head':obj(10)},'truncated':False}
def answer(choice,keys,confidence=.9):
    return {'model':'test','answers':{'target':{'type':'choice','choice':choice,'confidence':confidence,'probabilities':{k:1.0 if k==choice else 0.0 for k in keys}}}}

class WorkflowTests(unittest.TestCase):
    def test_reduction_and_protected(self):
        self.assertEqual(validate(plan(),scene(),scene(60))['status'],'pass')
        changed=scene(60);changed['objects']['Head']['mesh']['sha256']='other'
        self.assertEqual(validate(plan(),scene(),changed)['status'],'fail')
    def test_missing_truncated_and_bad_rule_fail(self):
        for missing in ('Head','Body'):
            after=scene(60);del after['objects'][missing]
            self.assertEqual(validate(plan(),scene(),after)['status'],'fail')
        after=scene(60);after['truncated']=True
        self.assertEqual(validate(plan(),scene(),after)['status'],'fail')
        bad=plan();bad['validation'][0]['kind']='looks_good'
        with self.assertRaises(ValueError):check_plan(bad)
    def test_boolean_threshold_and_target_overlap(self):
        for update in ({'protected_objects':['Body']},{'validation':[{'kind':'polygon_reduction','object':'Body','minimum':True}]}):
            p=plan();p.update(update)
            with self.assertRaises(ValueError):check_plan(p)
    def test_numeric_failure_cannot_be_overruled(self):
        with tempfile.TemporaryDirectory() as d:
            candidate=Path(d)/'candidate.blend';candidate.write_bytes(b'blend')
            result=completion(plan(),scene(),scene(90),candidate,decision={'candidate_id':'accept'})
            self.assertEqual(result['status'],'retry')
    def test_fuzzy_needs_observation_and_explicit_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            c=Path(d)/'candidate.blend';c.write_bytes(b'blend');img=Path(d)/'preview.png';img.write_bytes(b'PNG')
            p=plan();p['visual_requirements']=['silhouette']
            with self.assertRaises(ValueError):completion(p,scene(),scene(60),c)
            receipt=Path(d)/'render.json';receipt.write_text(json.dumps({'source_sha256':file_hash(c),'preview_sha256':file_hash(img)}))
            vision={'observer':'codex_vision','candidate_sha256':file_hash(c),'images':[{'path':str(img),'sha256':file_hash(img),'render_metadata':str(receipt)}],
                    'observations':[{'requirement':'silhouette','observation':'round outline remains','status':'observed'}]}
            result=completion(p,scene(),scene(60),c,vision)
            self.assertEqual(result['status'],'review')
            verdict={'origin':'independent_codex','action':'accept','reason':'outline preserved','evidence_sha256':result['evidence_sha256']}
            self.assertEqual(completion(p,scene(),scene(60),c,vision,verdict=verdict)['status'],'accepted')
            img.write_bytes(b'changed')
            with self.assertRaises(ValueError):completion(p,scene(),scene(60),c,vision,verdict=verdict)
    def test_fixture_not_live_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            c=Path(d)/'candidate.blend';c.write_bytes(b'blend');p=plan();b=scene();a=scene(60)
            state=evidence_state(p,b,a,validate(p,b,a),candidate_sha256=file_hash(c))
            request=prepare('completion',state)
            result=judge(request,answer('accept',request['request']['questions']['target']['criteria']),threshold=.7)
            self.assertEqual(result['origin'],'fixture')
            with self.assertRaises(ValueError):completion(p,b,a,c,decision=result)
    def test_stale_or_wrong_stage_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            c=Path(d)/'candidate.blend';c.write_bytes(b'blend')
            with self.assertRaises(ValueError):completion(plan(),scene(),scene(60),c,decision={'origin':'jev_live','stage':'risk'})
    def test_jev_failure_abstention_low_confidence(self):
        state=evidence_state(plan(),scene());p=prepare('risk',state);keys=p['request']['questions']['target']['criteria']
        self.assertEqual(judge(p,answer(ABSTAIN,keys),threshold=.6)['status'],'needs_codex')
        self.assertEqual(judge(p,answer('execute',keys,.4),threshold=.6)['reason'],'low_confidence')
        with self.assertRaises(ValueError):judge(p,answer('execute',keys),threshold=None)
    def test_malformed_service_evidence_is_preserved(self):
        p=prepare('risk',evidence_state(plan(),scene()))
        response=answer('execute',p['request']['questions']['target']['criteria'])
        response['answers']['target']['probabilities']['execute']=.5
        result=judge(p,response,threshold=.8)
        self.assertEqual(result['status'],'needs_codex');self.assertEqual(result['reason'],'invalid_service_response')
        self.assertEqual(result['service_response'],response)
    def test_compact_request_does_not_ship_modifier_properties_or_file_path(self):
        b=scene();b['scene']={'file':'/private/user/secret.blend'}
        b['objects']['Body']['modifiers']=[{'name':'mod','type':'NODES','properties':{'huge':'x'*10000}}]
        result=prepare('risk',evidence_state(plan(),b));state=result['request']['state']
        self.assertNotIn('file',state['before']['scene'])
        self.assertEqual(state['before']['objects']['Body']['modifiers'],[{'name':'mod','type':'NODES'}])
    def test_completion_does_not_rejudge_failed_validation(self):
        state=evidence_state(plan(),scene(),scene(90),validate(plan(),scene(),scene(90)),candidate_sha256='a'*64)
        with self.assertRaises(ValueError):prepare('completion',state)
    def test_retry_scope_and_budget(self):
        spec=retry(plan(),{'reason':'material_artifact','scope':'Body'})
        self.assertIn('geometry',spec['preserve']);self.assertIn('Head',spec['preserve_objects'])
        self.assertEqual(retry(plan(),{'reason':'material_artifact','scope':'Body'},3)['status'],'review')
        with self.assertRaises(ValueError):retry(plan(),{'reason':'material_artifact','scope':'Head'})
    def test_finalize_preserves_existing_file_and_binds_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=plan();b=scene();a=scene(60);c=root/'candidate.blend';c.write_bytes(b'blend')
            for name,value in [('plan',p),('before',b),('after',a)]: (root/f'{name}.json').write_text(json.dumps(value))
            result={'status':'staged','candidate_sha256':file_hash(c),'plan_sha256':fingerprint(p),'before_sha256':fingerprint(b),'after_sha256':fingerprint(a)}
            (root/'result.json').write_text(json.dumps(result));dest=root/'final.blend'
            self.assertEqual(finalize(root,dest)['status'],'accepted')
            with self.assertRaises(FileExistsError):finalize(root,dest)
            (root/'after.json').write_text('{}')
            with self.assertRaises(ValueError):finalize(root,root/'other.blend')
    def test_candidate_hash_is_part_of_completion_decision(self):
        with tempfile.TemporaryDirectory() as d:
            c=Path(d)/'one.blend';c.write_bytes(b'one');other=Path(d)/'two.blend';other.write_bytes(b'two')
            p=plan();b=scene();a=scene(60);state=evidence_state(p,b,a,validate(p,b,a),candidate_sha256=file_hash(c))
            decision={'origin':'jev_live','stage':'completion','status':'selected','candidate_id':'accept','evidence_sha256':fingerprint(state)}
            self.assertEqual(completion(p,b,a,c,decision=decision)['status'],'accepted')
            with self.assertRaises(ValueError):completion(p,b,a,other,decision=decision)
    def test_protected_evaluated_geometry_is_checked(self):
        a=scene(60);a['objects']['Head']['evaluated_mesh']['polygons']=99
        self.assertEqual(validate(plan(),scene(),a)['status'],'fail')
    def test_unknown_rule_fields_and_nonboolean_evaluated(self):
        for fields in ({'evaluated':'false'},{'minimun':.3}):
            p=plan();p['validation'][0].update(fields)
            with self.assertRaises(ValueError):check_plan(p)
    def test_predecision_cannot_override_or_use_stale_evidence(self):
        from workflow import predecision_gate
        p=plan();b=scene();binding=fingerprint(evidence_state(p,b))
        value={'origin':'codex','stage':'risk','status':'selected','candidate_id':'checkpoint_then_execute','evidence_sha256':binding}
        self.assertTrue(predecision_gate(p,b,value))
        for change in ({'candidate_id':'human_review'},{'origin':'fixture'},{'status':'needs_codex'},{'evidence_sha256':'stale'}):
            with self.assertRaises(ValueError):predecision_gate(p,b,{**value,**change})
    def test_benchmark_fixture_not_live(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'fixture.json';f.write_text('{"origin":"fixture"}')
            artifacts={key:str(f) for key in ('plan','before','after','validation','trace','pre_decision','post_decision')}
            with self.assertRaises(ValueError):record({'task_id':'x','category':'mesh_simplification'},'codex_jev',artifacts,'accepted')

if __name__=='__main__':unittest.main()
