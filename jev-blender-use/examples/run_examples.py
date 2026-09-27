#!/usr/bin/env python3
"""Run real Blender fixtures serially. Visual decisions remain pending for an observer."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from workflow import read, file_hash, validate, write_new, finalize

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--blender');p.add_argument('--output-dir',required=True);p.add_argument('--timeout',type=float,default=180)
    a=p.parse_args();out=Path(a.output_dir).resolve();out.mkdir(parents=True,exist_ok=False)
    records=[]
    def invoke(name,command,extra,expected='staged'):
        target=out/name
        cmd=[sys.executable,str(ROOT/'scripts/blender_cli.py'),command,'--output-dir',str(target),'--timeout',str(a.timeout)]
        if a.blender:cmd+=['--blender',a.blender]
        cmd+=extra
        with (out/(name+'.log')).open('wb') as log:
            proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=a.timeout+15)
        value=read(target/'result.json');records.append({'name':name,'status':value['status'],'exit_code':proc.returncode,'result':str(target/'result.json')})
        write_summary()
        if value['status']!=expected:raise RuntimeError(f'{name}: expected {expected}, got {value["status"]}; inspect log')
        return target
    def write_summary():
        (out/'summary.json').write_text(json.dumps({'runs':records,'vision':'pending_actual_observation','jev':'not_called'},indent=2)+'\n')
    def run(name,example,script,plan='plan.json',source=None,expected='staged'):
        args=['--plan',str(ROOT/'examples'/example/plan),'--script',str(ROOT/'examples'/example/script),'--trusted-script']
        if source:args+=['--source',str(source),'--source-sha256',file_hash(source)]
        return invoke(name,'run',args,expected)
    def render(name,source):
        return invoke(name,'render',['--source',str(source),'--width','384','--height','288','--samples','8'],'completed')
    def check(run):
        value=validate(read(run/'plan.json'),read(run/'before.json'),read(run/'after.json'));write_new(run/'validation.json',value)
        if value['status']!='pass':raise RuntimeError('validation failed: '+str(run))
    invoke('health','health',[],'completed')
    simple=run('simple','simple-scene','create.py');check(simple);render('simple-render',simple/'candidate.blend')
    mesh=run('mesh-fixture','mesh-optimization','setup.py','setup-plan.json');check(mesh)
    write_new(mesh/'acceptance.json',finalize(mesh,out/'mesh-source.blend'))
    render('mesh-before-render',mesh/'candidate.blend')
    optimized=run('mesh-optimized','mesh-optimization','optimize.py',source=mesh/'candidate.blend');check(optimized);render('mesh-after-render',optimized/'candidate.blend')
    forest=run('forest','geometry-nodes','create.py');check(forest);render('forest-render',forest/'candidate.blend')
    keyed=run('shape-key-fixture','jev-guard','setup.py','setup-plan.json');check(keyed)
    run('guard-refusal','jev-guard','apply.py',source=keyed/'candidate.blend',expected='refused')
    defect=run('material-defect','render-loop','setup.py','setup-plan.json');check(defect);render('material-before-render',defect/'candidate.blend')
    corrected=run('material-retry','render-loop','fix-material.py',source=defect/'candidate.blend');check(corrected);render('material-after-render',corrected/'candidate.blend')
    invoke('checkpoint','checkpoint',['--source',str(optimized/'candidate.blend'),'--source-sha256',file_hash(optimized/'candidate.blend')],'completed')
    print(json.dumps({'output_dir':str(out),'runs':len(records),'status':'deterministic_examples_passed','visual_review':'pending'},indent=2))
if __name__=='__main__':main()
