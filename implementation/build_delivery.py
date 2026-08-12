from __future__ import annotations
import argparse
import atexit
import csv
import json
import shutil
import subprocess
from pathlib import Path

REQUIRED={
 'README.md','registry_policy.json','release_policy.json','release_cases.csv','provenance_attestations.jsonl',
 'case_values/prod.yaml','case_values/canary.yaml','case_values/breakglass.yaml',
 'starter_chart/Chart.yaml','starter_chart/values.yaml','starter_chart/templates/deployment.yaml'
}
def run(command):
 result=subprocess.run(command,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=120)
 if result.returncode: raise RuntimeError(result.stdout+result.stderr)
 return result.stdout
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--output',required=True);parser.add_argument('--helm',required=True);args=parser.parse_args()
 source=Path(args.input).resolve();output=Path(args.output).resolve()
 if output.exists(): shutil.rmtree(output)
 finished={'ok':False}
 def cleanup():
  if not finished['ok'] and output.exists(): shutil.rmtree(output)
 atexit.register(cleanup)
 present={p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}
 if present!=REQUIRED: raise ValueError('发布材料集合发生变化')
 with (source/'release_cases.csv').open(encoding='utf-8-sig',newline='') as handle: cases=list(csv.DictReader(handle))
 policy=json.loads((source/'registry_policy.json').read_text(encoding='utf-8'))
 release=json.loads((source/'release_policy.json').read_text(encoding='utf-8'))
 if [r['case_id'] for r in cases]!=['prod','canary','breakglass']: raise ValueError('环境安排与版本组清单不一致')
 if policy['release_cases']!=[{k:(int(v) if k in {'replicas','stable_weight','canary_weight'} else v) for k,v in row.items()} for row in cases]: raise ValueError('仓库策略与环境清单不一致')
 summaries=[json.loads(line) for line in (source/'provenance_attestations.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
 expected={r['component']:(r['repository'],r['digest'],r['builder'],r['source_ref'],r['signature_state']) for r in policy['components']}
 actual={r['component']:(r['repository'],r['digest'],r['builder'],r['source_ref'],r['signature_state']) for r in summaries}
 if actual!=expected: raise ValueError('构建平台摘要与仓库策略不一致')
 chart=output/'chart';shutil.copytree(Path(__file__).resolve().parent/'chart',chart)
 values=chart/'values';rendered=output/'rendered';reports=output/'reports';values.mkdir(exist_ok=True);rendered.mkdir(parents=True);reports.mkdir()
 for row in cases: shutil.copy2(source/f"case_values/{row['case_id']}.yaml",values/f"{row['case_id']}.yaml")
 run([args.helm,'lint',str(chart),'--strict','-f',str(values/'prod.yaml')])
 inventory=[];weights=[]
 for row in cases:
  case_id=row['case_id'];value=values/f'{case_id}.yaml';manifest=run([args.helm,'template',row['release'],str(chart),'--namespace',row['namespace'],'-f',str(value)])
  (rendered/f'{case_id}.yaml').write_text(manifest,encoding='utf-8',newline='')
  if any(f"@{component['digest']}" not in manifest or component['repository'] not in manifest for component in policy['components']): raise ValueError('镜像来源未进入候选清单')
  stable=int(row['stable_weight']);canary=int(row['canary_weight'])
  if stable+canary!=100: raise ValueError('入口配置权重不闭合')
  kinds=[];names=[]
  for doc in manifest.split('\n---\n'):
   kind=next((line.split(':',1)[1].strip() for line in doc.splitlines() if line.startswith('kind:')),None)
   name=None
   lines=doc.splitlines()
   for i,line in enumerate(lines):
    if line.strip()=='metadata:':
     name=next((x.split(':',1)[1].strip() for x in lines[i+1:] if x.startswith('  name:')),None);break
   if kind and name: kinds.append(kind);names.append(name);inventory.append({'case_id':case_id,'namespace':row['namespace'],'kind':kind,'name':name})
  weights.append({'case_id':case_id,'stable_weight':stable,'canary_weight':canary,'configured_total':stable+canary,'ingress_count':kinds.count('Ingress')})
 with (reports/'rendered_objects.csv').open('w',encoding='utf-8',newline='') as handle:
  writer=csv.DictWriter(handle,fieldnames=list(inventory[0]),lineterminator='\n');writer.writeheader();writer.writerows(inventory)
 with (reports/'route_plan.csv').open('w',encoding='utf-8',newline='') as handle:
  writer=csv.DictWriter(handle,fieldnames=list(weights[0]),lineterminator='\n');writer.writeheader();writer.writerows(weights)
 with (reports/'image_sources.csv').open('w',encoding='utf-8',newline='') as handle:
  writer=csv.DictWriter(handle,fieldnames=['component','repository','digest','builder','source_ref','signature_state'],lineterminator='\n');writer.writeheader();writer.writerows(summaries)
 release_plan={**release,'available_case_ids':[r['case_id'] for r in cases]}
 (output/'release-plan.json').write_text(json.dumps(release_plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (output/'RELEASE-NOTES.md').write_text(f"支付入口候选Chart已按固定digest整理镜像引用。维护窗为{release['change_window']['start']}至{release['change_window']['end']}，影响{release['impact']}。先处理canary，观察{release['observation_minutes']}分钟后再决定prod；出现{release['rollback_condition']}时，{release['rollback_action']}。观察项为{'、'.join(release['observation_metrics'])}。breakglass参数留给已批准的应急窗口。\n",encoding='utf-8')
 (output/'README.md').write_text('chart目录保存支付入口候选Chart，rendered目录是三个已登记环境的候选清单，reports目录供发布经理核对对象、入口权重和镜像来源。release-plan.json和RELEASE-NOTES.md供值班团队安排维护窗。构建平台继续负责签名状态，集群管理员负责现场应用与运行观察。\n',encoding='utf-8')
 finished['ok']=True
if __name__=='__main__': main()
