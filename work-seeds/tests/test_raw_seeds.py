"""Small synthetic fixtures; no fixture records enter the official seed pool."""
import copy
from collections import defaultdict
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from emerging_tasks import merge_tasks, apply_regular_labels, classify_emerging, DataError
from sample_seeds import task_sample


def fixture():
    regular=[{'O*NET-SOC Code':'13-2031.00','Title':'Budget Analysts','Task ID':'1','Task':'Prepare budget reports.',
              'Task Type':'Core','Incumbents Responding':'1','Date':'08/2026','Domain Source':'Incumbent'},
             {'O*NET-SOC Code':'13-2031.00','Title':'Budget Analysts','Task ID':'2','Task':'Maintain budget records.',
              'Task Type':'Core','Incumbents Responding':'1','Date':'08/2026','Domain Source':'Incumbent'}]
    catalog={'occupations':{'13-2031.00':{'occupation_title':'Budget Analysts'}},
             'tasks':{r['Task ID']:{'task_id':r['Task ID'],'occupation_code':r['O*NET-SOC Code'],'task_text':r['Task']} for r in regular},
             'task_dwas':defaultdict(set,{'1':{'D1'},'2':{'D2'}})}
    emerging=[{'O*NET-SOC Code':'13-2031.00','Title':'Budget Analysts','Task':'Review budget spreadsheets.',
               'Category':'New','Original Task ID':'','Original Task':'','Date':'08/2026','Domain Source':'Incumbent'},
              {'O*NET-SOC Code':'13-2031.00','Title':'Budget Analysts','Task':'Prepare and reconcile budget reports.',
               'Category':'Revision','Original Task ID':'1','Original Task':regular[0]['Task'],'Date':'08/2026','Domain Source':'Incumbent'}]
    annotations={r['Task ID']:('2',{'O*NET-SOC Code':r['O*NET-SOC Code'],'Task':r['Task'],'Is Digital':'DIGITAL','Reason':'Fixture label'}) for r in regular}
    return catalog,regular,emerging,annotations


class RawSeedTests(unittest.TestCase):
    def test_new_and_revision_preserve_official_text_and_ids(self):
        c,raw,em,_=fixture();original=copy.deepcopy((c,raw,em))
        records,stats=merge_tasks(c,raw,em)
        self.assertEqual(len(records),3);self.assertNotIn('1',{r['task_id'] for r in records})
        self.assertEqual(stats['resolved_replacements'],1)
        for r in records:
            source=raw if r['task_source']=='regular' else em
            self.assertEqual(r['task_text'],source[r['source_metadata']['row']-2]['Task'])
            if r['task_source']!='regular':self.assertEqual(r['dwa_ids'],[])
        self.assertEqual((c,raw,em),original)
        self.assertEqual({r['task_id'] for r in records},{r['task_id'] for r in merge_tasks(c,raw,list(reversed(em)))[0]})

    def test_revision_reclassified_and_old_digital_never_returns(self):
        c,raw,em,a=fixture();records,_=merge_tasks(c,raw,em);apply_regular_labels(records,a)
        self.assertEqual(next(r for r in records if r['task_id']=='2')['digital_label'],'DIGITAL')
        received=[]
        def model(config,prompt,context,cache,**kwargs):
            received.extend(context['tasks'])
            return {'classifications':[{'task_id':r['task_id'],'digital_label':'PHYSICAL' if r['category']=='Revision' else 'UNCERTAIN','reason':'Fixture classification'} for r in context['tasks']]},{'request_sha256':'fixture'}
        with tempfile.TemporaryDirectory() as temp:
            classify_emerging(records,raw,{'model':'test','endpoint':'https://example.invalid'},Path(temp),caller=model,workers=1)
        self.assertEqual(len(received),2);self.assertTrue(all(r['task_id'].startswith('emerging_') for r in received))
        self.assertEqual([r['task_id'] for r in records if r['digital_label']=='DIGITAL'],['2'])
        self.assertEqual(next(r for r in received if r['category']=='Revision')['original_task_text'],raw[0]['Task'])

    def test_regular_annotations_exact_match_or_uncertain(self):
        c,raw,_,a=fixture();records,_=merge_tasks(c,raw,[])
        a['1'][1]['Task']='Different old text';a['2'][1]['Is Digital']='REVIEW'
        apply_regular_labels(records,a)
        self.assertTrue(all(r['digital_label']=='UNCERTAIN' for r in records))
        self.assertTrue(all(r['digital_label_source']=='AI4Work' for r in records))

    def test_unresolved_revision_never_fuzzy_matches(self):
        c,raw,em,_=fixture();em[1]['Original Task ID']='999'
        records,stats=merge_tasks(c,raw,em)
        self.assertIn('1',{r['task_id'] for r in records})
        self.assertFalse(any(r['task_source']=='emerging_revision' for r in records))
        self.assertEqual(stats['unresolved_revisions'][0]['reason'],'original_task_id_not_found')

    def test_latest_date_and_same_date_conflict(self):
        c,raw,em,_=fixture();old=copy.deepcopy(em[1]);old['Date']='08/2025';old['Task']='Older official revision.'
        records,stats=merge_tasks(c,raw,em+[old]);self.assertEqual(stats['resolved_replacements'],1)
        self.assertEqual(len(stats['superseded_revision_rows']),1)
        other=copy.deepcopy(em[1]);other['Task']='Different same-date revision.'
        records,stats=merge_tasks(c,raw,em+[other])
        self.assertEqual(stats['quarantined_original_task_ids'],['1'])
        self.assertNotIn('1',{r['task_id'] for r in records})
        self.assertFalse(any(r['task_source']=='emerging_revision' for r in records))

    def test_only_exact_duplicate_rows_removed(self):
        c,raw,em,_=fixture();records,stats=merge_tasks(c,raw,em+[copy.deepcopy(em[0])])
        self.assertEqual(len(records),3);self.assertEqual(stats['exact_duplicates_removed'],1)

    def test_llm_cannot_return_rewritten_content(self):
        c,raw,em,_=fixture();records,_=merge_tasks(c,raw,em)
        def bad(config,prompt,context,cache,**kwargs):
            return {'classifications':[{'task_id':r['task_id'],'digital_label':'DIGITAL','reason':'test','task_text':'rewritten'} for r in context['tasks']]},{'request_sha256':'fixture'}
        with tempfile.TemporaryDirectory() as temp,self.assertRaises(DataError):
            classify_emerging(records,raw,{'model':'test','endpoint':'https://example.invalid'},Path(temp),caller=bad,workers=1)

    def test_sampling_deterministic_and_dwa_absence_not_excluded(self):
        c,raw,em,_=fixture();records,_=merge_tasks(c,raw,em)
        cat={'tasks':{r['task_id']:{**r,'task_type':r['source_metadata']['task_type']} for r in records},
             'task_dwas':{r['task_id']:set(r['dwa_ids']) for r in records}}
        ids=list(cat['tasks']);x=task_sample(cat,ids,3,42,source_coverage=True)
        self.assertEqual(x,task_sample(cat,list(reversed(ids)),3,42,source_coverage=True))
        self.assertEqual(set(x),set(ids));self.assertEqual(len(set(x)),3)

    def test_new_source_gets_coverage_credit_without_invented_dwa(self):
        tasks={str(i):{'occupation_code':'13-2031.00','task_type':'Core','task_source':'regular'} for i in range(10)}
        tasks['new']={'occupation_code':'13-2031.00','task_type':'','task_source':'emerging_new'}
        tasks['revision']={'occupation_code':'13-2031.00','task_type':'','task_source':'emerging_revision'}
        links={t:({'D'+t} if t.isdigit() else set()) for t in tasks}
        cat={'tasks':tasks,'task_dwas':links}
        selected=task_sample(cat,list(tasks),3,42,source_coverage=True)
        self.assertEqual({tasks[t]['task_source'] for t in selected},{'regular','emerging_new','emerging_revision'})
        self.assertEqual(links['new'],set())


if __name__=='__main__':unittest.main()
