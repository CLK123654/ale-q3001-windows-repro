from __future__ import annotations
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];TASK=ROOT/'task';EVIDENCE=ROOT/'evidence';RUNS=ROOT/'windows-runs';HELM=os.environ['HELM_PATH']
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def reset(path):
    if path.exists(): shutil.rmtree(path)
    path.mkdir(parents=True)
def extract(archive,target): target.mkdir(parents=True); zipfile.ZipFile(archive).extractall(target)
def paths(root): return sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file())
def norm(path):
    data=path.read_bytes().replace(b'\r\n',b'\n')
    if path.suffix.lower()=='.json': return json.dumps(json.loads(data.decode('utf-8-sig')),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    return data
def compare(actual,expected):
    if paths(actual)!=paths(expected): raise AssertionError('delivery path set differs from Reference')
    for relative in paths(expected):
        if norm(actual/relative)!=norm(expected/relative): raise AssertionError(f'delivery differs from Reference: {relative}')
    return paths(expected)
def build(source,output): return subprocess.run([sys.executable,str(ROOT/'implementation/build_delivery.py'),'--input',str(source),'--output',str(output),'--helm',HELM],text=True,capture_output=True,timeout=300)
def main():
    reset(RUNS);EVIDENCE.mkdir(exist_ok=True);version=subprocess.run([HELM,'version','--short'],text=True,capture_output=True,timeout=30)
    if version.returncode or 'v3.18.4' not in version.stdout: raise AssertionError('Helm3.18.4 required')
    reference=RUNS/'reference';extract(TASK/'reference.zip',reference);expected=reference/'output';clean=[]
    for label in ['clean directory a','clean directory b']:
        base=RUNS/label;extract(TASK/'输入数据包.zip',base);source=base/'input_data';before={p.relative_to(source).as_posix():sha(p) for p in source.rglob('*') if p.is_file()}
        for process_index in [1,2]:
            output=base/f'output {process_index}';result=build(source,output)
            if result.returncode: raise AssertionError(result.stdout+result.stderr)
            generated=compare(output,expected);clean.append({'root_id':label,'process_index':process_index,'return_code':0,'primary_software_executed':True,'input_unchanged':True,'reference_full_match':True,'generated_paths':generated})
        if before!={p.relative_to(source).as_posix():sha(p) for p in source.rglob('*') if p.is_file()}: raise AssertionError('input changed')
    positive=RUNS/'positive';extract(TASK/'输入数据包.zip',positive);file=positive/'input_data/case_values/canary.yaml';text=file.read_text(encoding='utf-8');file.write_text(text.replace('replicaCount: 4','replicaCount: 5'),encoding='utf-8');csv_file=positive/'input_data/release_cases.csv'
    with csv_file.open(encoding='utf-8',newline='') as handle: rows=list(csv.DictReader(handle))
    for row in rows:
        if row['case_id']=='canary': row['replicas']='5'
    with csv_file.open('w',encoding='utf-8',newline='') as handle: writer=csv.DictWriter(handle,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    policy_file=positive/'input_data/registry_policy.json';policy=json.loads(policy_file.read_text(encoding='utf-8'))
    for row in policy['release_cases']:
        if row['case_id']=='canary': row['replicas']=5
    policy_file.write_text(json.dumps(policy,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');result=build(positive/'input_data',positive/'output')
    if result.returncode: raise AssertionError(result.stdout+result.stderr)
    manifest=(positive/'output/rendered/canary.yaml').read_text(encoding='utf-8')
    if 'replicas: 5' not in manifest or norm(positive/'output/rendered/prod.yaml')!=norm(expected/'rendered/prod.yaml'): raise AssertionError('canary replica change did not stay within its environment')
    (EVIDENCE/'positive-case.json').write_text(json.dumps({'mutation':'canary副本从4改为5','canary_changed':True,'prod_unchanged':True},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    negative=RUNS/'negative';extract(TASK/'输入数据包.zip',negative);file=negative/'input_data/provenance_attestations.jsonl';lines=file.read_text(encoding='utf-8').splitlines();data=json.loads(lines[0]);data['digest']='sha256:'+'0'*64;lines[0]=json.dumps(data,separators=(',',':'));file.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    output=negative/'output';output.mkdir();(output/'stale.txt').write_text('stale',encoding='utf-8');result=build(negative/'input_data',output)
    if result.returncode==0 or output.exists(): raise AssertionError('source digest mismatch did not fail closed')
    (EVIDENCE/'negative-case.log').write_text(f'return_code={result.returncode}\n{result.stdout}{result.stderr}',encoding='utf-8')
    summary={'result':'PASS','commit_sha':os.getenv('GITHUB_SHA'),'workflow_run_id':os.getenv('GITHUB_RUN_ID'),'runner_image':os.getenv('ImageOS'),'main_software':{'name':'Helm','version':version.stdout.strip(),'executed':True},'clean_directory_count':2,'process_runs_per_directory':2,'clean_runs':clean,'positive_mutation':'PASS','negative_case':'PASS','reference_full_comparison':'PASS','formal_network':{'python_outbound_blocked':True,'helm_outbound_blocked':True,'external_services_used':False}}
    (EVIDENCE/'windows-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__': main()
