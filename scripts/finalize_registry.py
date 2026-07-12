# -*- coding: utf-8 -*-
"""D-22 去重 + D-21 版本归组 + 终检 + 产物输出(幂等,可重跑)"""
import json, re, sqlite3, csv, os, shutil
from collections import defaultdict
JL='/sessions/peaceful-vigilant-hopper/mnt/metadata_output/registry.jsonl'
OUT='/sessions/peaceful-vigilant-hopper/mnt/metadata_output/'
recs={}
for line in open(JL,encoding='utf-8'):
    r=json.loads(line); recs[r['doc_id']]=r
recs=list(recs.values())
# 人工覆盖层(最高优先级, 2026-07-05 用户审查)
import json as _j
MAN_D=_j.load(open('/sessions/peaceful-vigilant-hopper/mnt/outputs/manual_dates.json',encoding='utf-8'))
import os as _o
_mt='/sessions/peaceful-vigilant-hopper/mnt/metadata_output/manual_titles.json'
MAN_T=_j.load(open(_mt,encoding='utf-8')) if _o.path.exists(_mt) else {}
for r in recs:
    if r['file_path'].replace(chr(92),'/') in MAN_T:
        r['doc_title']=MAN_T[r['file_path'].replace(chr(92),'/')]; r['title_source']='manual' 
UNGROUP=set(_j.load(open('/sessions/peaceful-vigilant-hopper/mnt/outputs/manual_ungroup.json',encoding='utf-8')))
man_applied=0
for r in recs:
    if r['file_path'] in MAN_D and MAN_D[r['file_path']] != r.get('effective_date'):
        r['effective_date']=MAN_D[r['file_path']]; r['date_source']='manual'; man_applied+=1
print('人工日期覆盖生效:',man_applied,'| 摘除名单:',len(UNGROUP))
FMT_PRI={'docx':0,'doc_converted':1,'txt':2,'xlsx':3}
by_fp=defaultdict(list)
for r in recs:
    if r.get('fingerprint'): by_fp[r['fingerprint']].append(r)
dup_rows=[]
for fp,grp in by_fp.items():
    if len(grp)<2: continue
    grp.sort(key=lambda r:(FMT_PRI.get(r['format'],9),-r['size']))
    canon=grp[0]
    for d in grp[1:]:
        d['duplicate_of']=canon['doc_id']
        dup_rows.append([d['file_path'],d['format'],canon['file_path'],canon['format'],(d.get('doc_title') or '')[:50]])
INVIS=re.compile(r'[​‌‍﻿　\s]')
def norm_title(t):
    if not t: return None
    t=INVIS.sub('',re.sub(r'[《》]','',t))
    t=re.sub(r'[(（]\d{4}.*?[修订正].*?[)）]$','',t)
    return t if t and len(t)>=6 else None
by_title=defaultdict(list)
for r in recs:
    if r.get('duplicate_of') or str(r.get('status','')).startswith('ERROR'): continue
    if r['file_path'] in UNGROUP: continue  # 用户标注:主题不同,误归组
    nt=norm_title(r.get('doc_title')) if r.get('title_source')!='FAIL' else None
    if nt: by_title[nt].append(r)
ver_rows=[]; ambiguous=0
for nt,grp in by_title.items():
    if len(grp)<2: continue
    grp.sort(key=lambda r:(r.get('effective_date') or '0000'),reverse=True)
    amb=(grp[0].get('effective_date') is None) or (grp[0].get('effective_date')==grp[1].get('effective_date'))
    if amb: ambiguous+=1
    for i,r in enumerate(grp):
        r['version_group']=nt; r['is_latest']=1 if i==0 else 0
        ver_rows.append([nt[:44],r['file_path'],r.get('effective_date') or '?','latest' if i==0 else 'old','AMBIGUOUS' if amb else ''])
for r in recs:
    if r.get('is_latest') is None and not r.get('duplicate_of'): r['is_latest']=1
fails=[[r['file_path'],r['format'],(r.get('doc_title') or '')[:60]] for r in recs if r.get('title_source')=='FAIL']
tmp='/tmp/registry.sqlite'
if os.path.exists(tmp): os.remove(tmp)
con=sqlite3.connect(tmp)
cols=['doc_id','file_path','format','size','mtime','content_hash','doc_version','fingerprint',
      'doc_title','title_source','effective_date','source_url','issuing_org',
      'duplicate_of','version_group','is_latest','status','tenant_id']
con.execute(f'CREATE TABLE documents ({",".join(cols)}, PRIMARY KEY(doc_id))')
for r in recs: con.execute(f'INSERT INTO documents VALUES ({",".join("?"*len(cols))})',[r.get(c) for c in cols])
con.commit()
q=lambda s: con.execute(s).fetchall()
vg=len([1 for g in by_title.values() if len(g)>1])
print(f'登记 {len(recs)} | 重复 {len(dup_rows)} | 版本组 {vg}(模糊 {ambiguous}) | title FAIL {len(fails)}')
print('title来源:',q("SELECT title_source,COUNT(*) FROM documents GROUP BY title_source"))
print('有date:',q("SELECT COUNT(*) FROM documents WHERE effective_date IS NOT NULL")[0][0],
      '| 可索引:',q("SELECT COUNT(*) FROM documents WHERE duplicate_of IS NULL")[0][0],
      '| 最新版:',q("SELECT COUNT(*) FROM documents WHERE duplicate_of IS NULL AND is_latest=1")[0][0])
print('企业所得税法组:',q("SELECT file_path,effective_date,is_latest FROM documents WHERE version_group='中华人民共和国企业所得税法'"))
con.close()
shutil.copy(tmp, OUT+'registry.sqlite')
def w(name,hdr,rows):
    with open(OUT+name,'w',newline='',encoding='utf-8-sig') as f:
        cw=csv.writer(f); cw.writerow(hdr); cw.writerows(rows)
w('review_duplicates.csv',['重复文件','格式','保留(canonical)','格式','标题'],dup_rows)
w('review_version_groups_v2.csv',['版本组','文件','日期','状态','需人工裁决'],sorted(ver_rows))
w('review_title_fail.csv',['文件','格式','首段(疑似非标题)'],fails)
print('registry.sqlite + 3 CSV 已输出')
