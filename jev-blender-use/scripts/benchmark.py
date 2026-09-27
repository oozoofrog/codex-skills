#!/usr/bin/env python3
"""Immutable per-attempt benchmark records and scoped retry proposals. No execution."""
import argparse
import json
from pathlib import Path
import sys
from workflow import read, write_new, file_hash, check_plan, validate, evidence_state, fingerprint, predecision_gate

VARIANTS=('codex_only','codex_validation','codex_jev','codex_jev_vision')
TAXONOMY=('object_rename','object_transform','material_replacement','mesh_simplification','uv_repair',
 'normal_repair','camera_composition','lighting','modifier_optimization','geometry_nodes',
 'armature_repair','game_asset','procedural_scene','render_configuration','scene_cleanup')

def retry(plan,failure,attempt=1,max_attempts=3):
    check_plan(plan)
    if type(attempt) is not int or type(max_attempts) is not int or not 1<=attempt<=max_attempts<=20:
        raise ValueError('invalid retry budget')
    scope=failure.get('scope');reason=failure.get('reason')
    if scope not in plan['target_objects']:raise ValueError('retry must name an existing target')
    mapping={'material_artifact':('materials',['geometry','transform','modifiers']),
             'geometry_artifact':('geometry',['materials','transform']),
             'camera_problem':('transform',['geometry','materials','modifiers'])}
    if reason not in mapping:raise ValueError('unknown failure: inspect before proposing retry')
    changed,preserve=mapping[reason]
    if attempt>=max_attempts:return {'status':'review','reason':'retry_budget_exhausted'}
    return {'schema_version':1,'status':'retry','reason':reason,'scope':[scope],
            'change_only':changed,'preserve':preserve,'preserve_objects':[n for n in plan['target_objects'] if n!=scope]+plan.get('protected_objects',[]),
            'attempt':attempt+1,'max_attempts':max_attempts,
            'validation_to_add':[{'kind':'unchanged','object':scope,'aspect':x} for x in preserve],
            'instruction':'Use previous candidate as baseline. Inspect again, review new script, and rerun protected checks. Do not automatically rerun a timed-out mutation.'}

def record(task,variant,artifacts,status,human_verdict=None):
    if variant not in VARIANTS or task.get('category') not in TAXONOMY or not task.get('task_id'):
        raise ValueError('invalid task taxonomy or variant')
    required={'plan','before','after','validation','trace','candidate'}
    if not required<=set(artifacts):raise ValueError('missing benchmark evidence')
    if variant in ('codex_jev','codex_jev_vision') and not {'pre_decision','post_decision'}<=set(artifacts):
        raise ValueError('Jev variant requires actual decision records')
    if variant=='codex_jev_vision' and not {'vision','render'}<=set(artifacts):raise ValueError('Vision variant requires observations/render')
    refs={name:{'path':str(Path(path).resolve()),'sha256':file_hash(path)} for name,path in artifacts.items()}
    origins={}
    effective_origins={}
    plan,before,after=(read(artifacts[n]) for n in ('plan','before','after'))
    actual_validation=validate(plan,before,after)
    if read(artifacts['validation'])!=actual_validation:raise ValueError('benchmark validation is stale')
    for name in ('pre_decision','post_decision'):
        if name in artifacts:
            value=read(artifacts[name]);origins[name]=value.get('origin')
            if variant in ('codex_jev','codex_jev_vision') and (origins[name]!='jev_live' or value.get('status') not in ('selected','needs_codex') or not value.get('model') or not isinstance(value.get('answer'),dict)):
                raise ValueError('mock/prepared/unavailable decisions cannot count as live Jev benchmark')
            expected_stage=('risk','strategy') if name=='pre_decision' else ('completion',)
            if value.get('stage') not in expected_stage:raise ValueError('benchmark decision stage mismatch')
            state=evidence_state(plan,before) if name=='pre_decision' else evidence_state(plan,before,after,actual_validation,
                read(artifacts['vision']) if 'vision' in artifacts else None,file_hash(artifacts['candidate']))
            if value.get('evidence_sha256')!=fingerprint(state):raise ValueError('benchmark decision evidence mismatch')
            from decision import prepare
            from jev_select import interpret
            payload=prepare(value['stage'],state,value.get('requested_model','jev-latest'))['request']
            normalized=interpret({'model':value['model'],'answers':{'target':value['answer']}},payload,value.get('min_confidence'))
            if any(value.get(k)!=normalized.get(k) for k in ('status','candidate_id','reason')):
                raise ValueError('benchmark decision interpretation mismatch')
            effective_origins[name]='jev_live' if value['status']=='selected' else 'unresolved'
            if name=='pre_decision' and value['status']!='selected' and status=='accepted':
                if 'pre_fallback' not in artifacts:raise ValueError('accepted run needs recorded predecision fallback')
                fallback=read(artifacts['pre_fallback']);predecision_gate(plan,before,fallback)
                effective_origins[name]=fallback['origin']
            if name=='post_decision' and status=='accepted' and value.get('candidate_id')!='accept':
                raise ValueError('accepted Jev benchmark needs accepting postdecision; record fallback cohort separately')
    return {'schema_version':1,'task':task,'variant':variant,'artifacts':refs,'decision_origins':origins,'effective_decision_origins':effective_origins,
            'final_status':status,'human_verdict':human_verdict,
            'comparison':'record only; does not establish quality gain or equivalence across variants'}

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('retry');r.add_argument('--plan',required=True);r.add_argument('--failure',required=True);r.add_argument('--attempt',type=int,default=1);r.add_argument('--max-attempts',type=int,default=3)
    b=sub.add_parser('record');b.add_argument('--task',required=True);b.add_argument('--variant',choices=VARIANTS,required=True);b.add_argument('--artifacts',required=True);b.add_argument('--status',choices=['accepted','retry','review','failed'],required=True);b.add_argument('--human-verdict')
    for x in (r,b):x.add_argument('--output',required=True)
    a=p.parse_args()
    try:
        value=retry(read(a.plan),read(a.failure),a.attempt,a.max_attempts) if a.command=='retry' else record(read(a.task),a.variant,read(a.artifacts),a.status,a.human_verdict)
        write_new(a.output,value);print(json.dumps(value,indent=2));return 0
    except (ValueError,KeyError,TypeError,OSError) as e:print(json.dumps({'status':'review','reason':str(e)}));return 2
if __name__=='__main__':sys.exit(main())
