#!/usr/bin/env python3
"""Exact validation and artifact-bound completion. No Blender or model dependency."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
from jev_select import encoded, fingerprint

ASPECTS = {'geometry': ('mesh', 'sha256'), 'transform': ('transform',),
           'materials': ('material_sha256',), 'modifiers': ('modifier_sha256',)}
RULES = {'exists', 'absent', 'unchanged', 'polygon_reduction', 'max_polygons',
         'max_nonmanifold_edges', 'max_degenerate_faces', 'max_winding_conflicts', 'modifier_exists', 'instance_count'}

def read(path):
    p = Path(path)
    if p.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('JSON input exceeds 4 MiB; narrow evidence')
    return json.loads(p.read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))

def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def write_new(path, value):
    with Path(path).open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

def names(value, field):
    if not isinstance(value, list) or len(value) > 100 or any(not isinstance(x, str) or not x for x in value) or len(set(value)) != len(value):
        raise ValueError(f'{field} requires at most 100 unique names')
    return value

def check_plan(plan):
    if not isinstance(plan, dict) or type(plan.get('schema_version')) is not int or plan['schema_version'] != 1:
        raise ValueError('plan schema_version must be 1')
    if set(plan)-{'schema_version','task_id','goal','target_objects','protected_objects','operations','validation','visual_requirements'}:
        raise ValueError('unknown plan fields')
    for key in ('task_id', 'goal'):
        if not isinstance(plan.get(key), str) or not plan[key].strip():
            raise ValueError(f'plan needs {key}')
    targets = names(plan.get('target_objects'), 'target_objects')
    protected = names(plan.get('protected_objects', []), 'protected_objects')
    if set(targets) & set(protected):
        raise ValueError('target/protected overlap')
    operations = plan.get('operations')
    if not isinstance(operations, list) or not operations or len(operations) > 100:
        raise ValueError('plan needs 1..100 operations')
    for op in operations:
        if not isinstance(op, dict) or not isinstance(op.get('type'), str) or not op['type']:
            raise ValueError('operation needs type')
        if op.get('target') is not None and op['target'] not in targets:
            raise ValueError('operation target must be declared')
    rules = plan.get('validation')
    if not isinstance(rules, list) or not rules:
        raise ValueError('at least one deterministic validation is required')
    for rule in rules:
        if not isinstance(rule, dict) or rule.get('kind') not in RULES or not isinstance(rule.get('object'), str):
            raise ValueError('unsupported validation rule')
        fields={'kind','object'} | ({'aspect'} if rule['kind']=='unchanged' else {'minimum','evaluated'} if rule['kind']=='polygon_reduction' else {'maximum','evaluated'} if rule['kind'].startswith('max_') else {'modifier'} if rule['kind']=='modifier_exists' else {'count'} if rule['kind']=='instance_count' else set())
        if set(rule)-fields:raise ValueError('unknown validation fields')
        if 'evaluated' in rule and type(rule['evaluated']) is not bool:raise ValueError('evaluated must be boolean')
        if rule['kind']=='modifier_exists' and (not isinstance(rule.get('modifier'),str) or not rule['modifier']):raise ValueError('modifier type required')
        if rule['kind'] == 'unchanged' and rule.get('aspect') not in ASPECTS:
            raise ValueError('unknown unchanged aspect')
        if rule['kind'] == 'polygon_reduction':
            n = rule.get('minimum')
            if type(n) not in (int, float) or not math.isfinite(n) or not 0 < n <= 1:
                raise ValueError('minimum reduction must be in (0,1]')
        if rule['kind'] == 'instance_count' and (type(rule.get('count')) is not int or rule['count'] < 0):
            raise ValueError('instance count must be a nonnegative integer')
        if rule['kind'].startswith('max_') and (type(rule.get('maximum')) is not int or rule['maximum'] < 0):
            raise ValueError('maximum must be nonnegative integer')
    visual = plan.get('visual_requirements', [])
    if not isinstance(visual, list) or any(not isinstance(x, str) or not x for x in visual):
        raise ValueError('visual_requirements must be strings')
    return plan

def aspect(obj, key):
    for part in ASPECTS[key]:
        obj = obj[part]
    if obj is None:
        raise ValueError('aspect unavailable')
    return obj

def validate(plan, before, after):
    check_plan(plan)
    checks = []
    if before.get('truncated') or after.get('truncated'):
        checks.append({'kind': 'complete_evidence', 'pass': False, 'reason': 'narrow scope and reinspect'})
    rules = list(plan['validation'])
    for name in plan.get('protected_objects', []):
        for key in ASPECTS:
            # Mesh identity is applicable only to mesh objects, other facets always apply.
            if key != 'geometry' or before.get('objects', {}).get(name, {}).get('type') == 'MESH':
                rules.append({'kind': 'unchanged', 'object': name, 'aspect': key})
    from scene_worker import protected_changed
    changes = protected_changed({'protected_objects':plan.get('protected_objects',[])},before,after)
    checks.extend({'kind':'protected_state','object':x['object'],'pass':False,'changed_fields':x['fields']} for x in changes)
    for rule in rules:
        name, kind = rule['object'], rule['kind']
        b, a = before.get('objects', {}).get(name), after.get('objects', {}).get(name)
        row = {**rule, 'pass': False}
        try:
            if kind in ('exists', 'absent'):
                row['pass'] = (a is not None) if kind == 'exists' else (a is None)
            elif kind == 'unchanged':
                bv, av = aspect(b, rule['aspect']), aspect(a, rule['aspect'])
                row.update(before=bv, after=av, **{'pass': bv == av})
            elif kind == 'instance_count':
                row['after'] = a['evaluated_instances']['count']
                row['pass'] = row['after'] == rule['count']
            elif kind == 'modifier_exists':
                row['pass'] = any(m.get('type') == rule.get('modifier') for m in a['modifiers'])
            else:
                mesh = 'evaluated_mesh' if rule.get('evaluated', True) else 'mesh'
                key = {'polygon_reduction':'polygons', 'max_polygons':'polygons',
                       'max_nonmanifold_edges':'nonmanifold_edges', 'max_degenerate_faces':'degenerate_faces','max_winding_conflicts':'winding_conflicts'}[kind]
                av = a[mesh][key]
                if type(av) not in (int, float) or not math.isfinite(av) or av < 0:
                    raise ValueError('invalid mesh metric')
                row['after'] = av
                if kind == 'polygon_reduction':
                    bv = b[mesh][key]
                    if type(bv) not in (int, float) or bv <= 0:
                        raise ValueError('positive baseline required')
                    reduction = (bv-av)/bv
                    row.update(before=bv, reduction=reduction, **{'pass': reduction >= rule['minimum']})
                else:
                    row['pass'] = av <= rule['maximum']
        except (KeyError, TypeError, ValueError):
            row['reason'] = 'missing_or_invalid_evidence'
        checks.append(row)
    return {'schema_version':1, 'status':'pass' if all(c['pass'] for c in checks) else 'fail',
            'plan_sha256':fingerprint(plan), 'before_sha256':fingerprint(before),
            'after_sha256':fingerprint(after), 'checks':checks}

def evidence_state(plan, before, after=None, validation=None, vision=None, candidate_sha256=None):
    """Bound complete local evidence; callers may transmit a smaller explicit summary."""
    return {'plan':plan, 'before':before, 'after':after,
            'validation':validation, 'vision':vision, 'candidate_sha256':candidate_sha256}

def check_vision(vision, plan, candidate_hash):
    if not plan.get('visual_requirements'):
        return
    if not isinstance(vision, dict) or vision.get('observer') not in ('codex_vision','independent_codex_vision','human'):
        raise ValueError('visual requirements need identified observer')
    if vision.get('candidate_sha256') != candidate_hash:
        raise ValueError('vision is stale')
    images = vision.get('images')
    if not isinstance(images, list) or not images:
        raise ValueError('visual observation needs image evidence')
    for item in images:
        if file_hash(item['path']) != item['sha256']:
            raise ValueError('image evidence changed')
        receipt=read(item['render_metadata'])
        if receipt.get('source_sha256')!=candidate_hash or receipt.get('preview_sha256')!=item['sha256']:
            raise ValueError('render evidence does not belong to candidate')
    observations = vision.get('observations')
    if not isinstance(observations, list) or any(not isinstance(x, dict) for x in observations):
        raise ValueError('structured observations required')
    if {x.get('requirement') for x in observations} != set(plan['visual_requirements']):
        raise ValueError('each visual requirement must be observed')
    for row in observations:
        if not isinstance(row.get('observation'), str) or not row['observation'].strip() or row.get('status') not in ('observed','uncertain'):
            raise ValueError('invalid visual observation')
        if row['status'] == 'uncertain':
            raise ValueError('unresolved visual observation')

def completion(plan, before, after, candidate, vision=None, decision=None, verdict=None):
    report = validate(plan, before, after)
    if report['status'] != 'pass':
        return {'status':'retry', 'reason':'deterministic_failure', 'failures':[c for c in report['checks'] if not c['pass']]}
    candidate_hash = file_hash(candidate)
    check_vision(vision, plan, candidate_hash)
    state = evidence_state(plan, before, after, report, vision, candidate_hash)
    binding = fingerprint(state)
    if decision is not None:
        if decision.get('stage') != 'completion' or decision.get('evidence_sha256') != binding:
            raise ValueError('decision stage/evidence mismatch')
        if decision.get('origin') != 'jev_live':
            raise ValueError('fixture/prepared decisions cannot authorize acceptance')
        if decision.get('status') != 'selected':
            return {'status':'review', 'reason':decision.get('reason','uncertain_decision')}
        action = decision.get('candidate_id')
    elif plan.get('visual_requirements'):
        if not isinstance(verdict, dict) or verdict.get('evidence_sha256') != binding or verdict.get('origin') not in ('codex','independent_codex','human'):
            return {'status':'review', 'reason':'fuzzy_requirement_needs_explicit_verdict', 'evidence_sha256':binding}
        if not isinstance(verdict.get('reason'), str) or not verdict['reason'].strip():
            raise ValueError('fallback verdict needs a reason')
        action = verdict.get('action')
    else:
        action = 'accept'
    if action not in ('accept','retry_geometry','retry_material','retry_camera','rerender','human_review'):
        return {'status':'review', 'reason':'unsupported_completion_action'}
    return {'status':'accepted' if action == 'accept' else 'review' if action == 'human_review' else 'retry',
            'action':action, 'evidence_sha256':binding, 'candidate_sha256':candidate_hash,
            'decision_origin':decision.get('origin') if decision else verdict.get('origin') if verdict else 'deterministic',
            'validation':report}

def load_staged_run(run_dir):
    """Read a candidate and verify its existing execution bindings."""
    run = Path(run_dir).resolve(); result = read(run/'result.json')
    if result.get('status') != 'staged':
        raise ValueError('completion evidence requires a staged run')
    plan, before, after = (read(run/f'{x}.json') for x in ('plan','before','after'))
    candidate = run/'candidate.blend'
    if file_hash(candidate) != result.get('candidate_sha256'):
        raise ValueError('candidate changed after execution')
    if fingerprint(plan) != result.get('plan_sha256'):
        # Host may use exact bytes; also accept exact snapshotted plan hash.
        if file_hash(run/'plan.json') != result.get('plan_sha256'):
            raise ValueError('plan changed after execution')
    for label, value in [('before',before),('after',after)]:
        expected = result.get(f'{label}_sha256')
        if expected is None or expected not in (fingerprint(value),file_hash(run/f'{label}.json')):
            raise ValueError(f'{label} evidence changed or lacks execution binding')
    return plan, before, after, candidate


def completion_state(run_dir, vision=None):
    """Build locally bound evidence without inventing observations or a judgment."""
    plan, before, after, candidate = load_staged_run(run_dir)
    report = validate(plan, before, after)
    if report['status'] != 'pass':
        raise ValueError('completion state requires deterministic PASS; inspect validation failures')
    candidate_hash = file_hash(candidate)
    check_vision(vision, plan, candidate_hash)
    return evidence_state(plan, before, after, report, vision, candidate_hash)


def recorded_verdict(run_dir, vision, action, reason, origin='codex'):
    """Bind a caller-supplied judgment; never select accept automatically."""
    if origin not in ('codex', 'independent_codex', 'human'):
        raise ValueError('verdict requires an identified evaluator')
    if action not in ('accept', 'retry_geometry', 'retry_material', 'retry_camera', 'rerender', 'human_review'):
        raise ValueError('unsupported verdict action')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('verdict needs the evaluator reason')
    state = completion_state(run_dir, vision)
    return {'origin': origin, 'action': action, 'reason': reason,
            'evidence_sha256': fingerprint(state)}


def finalize(run_dir, destination, vision=None, decision=None, verdict=None):
    plan, before, after, candidate = load_staged_run(run_dir)
    outcome = completion(plan,before,after,candidate,vision,decision,verdict)
    if outcome['status'] != 'accepted':
        return outcome
    dest = Path(destination).expanduser().absolute()
    if dest.suffix != '.blend':
        raise ValueError('destination must be a new .blend file')
    # Exclusive create prevents overwrite even if another process creates destination.
    with candidate.open('rb') as source, dest.open('xb') as out:
        shutil.copyfileobj(source,out)
    if file_hash(dest) != outcome['candidate_sha256']:
        raise ValueError('final copy verification failed; preserve evidence')
    outcome['saved_file'] = str(dest)
    return outcome

def predecision_gate(plan, before, decision):
    if decision is None:
        return False
    if decision.get('stage') != 'risk' or decision.get('evidence_sha256') != fingerprint(evidence_state(plan,before)):
        raise ValueError('predecision is stale or not a risk decision')
    if decision.get('origin') not in ('jev_live','codex','independent_codex','human') or decision.get('status') != 'selected':
        raise ValueError('predecision is not an actionable live/fallback judgment')
    action=decision.get('candidate_id')
    if action not in ('execute','checkpoint_then_execute'):
        raise ValueError('predecision requires alternative or review')
    return action=='checkpoint_then_execute'


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    v=sub.add_parser('validate'); v.add_argument('--plan',required=True); v.add_argument('--before',required=True); v.add_argument('--after',required=True)
    f=sub.add_parser('finalize'); f.add_argument('--run-dir',required=True); f.add_argument('--destination',required=True)
    for arg in ('vision','decision','verdict'): f.add_argument('--'+arg)
    state = sub.add_parser('completion-state', help='Assemble bound evidence for an optional Jev completion call')
    verdict = sub.add_parser('verdict', help='Record an explicit Codex or evaluator judgment with current evidence')
    for item in (state, verdict):
        item.add_argument('--run-dir', required=True)
        item.add_argument('--vision')
        item.add_argument('--output', required=True, help='New JSON file; existing files are preserved')
    verdict.add_argument('--action', required=True, choices=('accept','retry_geometry','retry_material','retry_camera','rerender','human_review'))
    verdict.add_argument('--reason', required=True)
    verdict.add_argument('--origin', default='codex', choices=('codex','independent_codex','human'))
    for s in (v,f): s.add_argument('--output')
    args=p.parse_args()
    try:
        if args.command=='validate': result=validate(read(args.plan),read(args.before),read(args.after))
        elif args.command == 'completion-state':
            result = completion_state(args.run_dir, read(args.vision) if args.vision else None)
        elif args.command == 'verdict':
            result = recorded_verdict(args.run_dir, read(args.vision) if args.vision else None,
                                      args.action, args.reason, args.origin)
        else: result=finalize(args.run_dir,args.destination,**{k:read(getattr(args,k)) if getattr(args,k) else None for k in ('vision','decision','verdict')})
        if args.output: write_new(args.output,result)
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 0 if args.command in ('completion-state','verdict') or result['status'] in ('pass','accepted') else 2
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({'status':'review','reason':str(exc)})); return 2

if __name__=='__main__': sys.exit(main())
