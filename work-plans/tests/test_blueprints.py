"""Synthetic graph fixtures are isolated from real pilot records."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from plan_intents import validate_blueprint,validate_review,load_raw,DataError,run


def fixture():
    return {'seed_id':'synthetic_test_fixture','work_objective':'Compare requested amounts with recorded amounts.',
            'deliverables':[{'id':'out1','type':'report','description':'Comparison of the amounts','preferred_formats':['md']}],
            'information_nodes':[{'id':'i1','type':'external_input','description':'Recorded amounts','supply_channel':'workspace','critical':True,'kind':'table','preferred_formats':['csv'],'modality_candidates':[],'modality_rationale':''},
                                 {'id':'i2','type':'derived_information','description':'Differences between the amounts'}],
            'dependencies':[['i1','i2'],['i2','out1']],'modality_hypotheses':[]}


class BlueprintTests(unittest.TestCase):
    def check(self,p):return validate_blueprint(p,{'seed_id':'synthetic_test_fixture'})
    def test_valid_graph(self):self.assertTrue(all(self.check(fixture()).values()))
    def test_unknown_seed(self):
        p=fixture();p['seed_id']='wrong'
        with self.assertRaisesRegex(DataError,'seed_id'):self.check(p)
    def test_duplicate_and_unknown_nodes_edges(self):
        for change in ('node','edge','unknown'):
            p=fixture()
            if change=='node':p['information_nodes'].append(copy.deepcopy(p['information_nodes'][0]))
            elif change=='edge':p['dependencies'].append(['i1','i2'])
            else:p['dependencies'].append(['i9','out1'])
            with self.assertRaises(DataError):self.check(p)
    def test_cycle_missing_premise_and_unused_node(self):
        for kind in ('cycle','premise','unused','root','sink'):
            p=fixture()
            if kind=='cycle':
                p['information_nodes'].append({'id':'i3','type':'derived_information','description':'Other derivation'})
                p['dependencies'] += [['i2','i3'],['i3','i2']]
            elif kind=='premise':p['dependencies'].remove(['i1','i2'])
            elif kind=='unused':p['information_nodes'].append({**p['information_nodes'][0],'id':'unused'})
            elif kind=='root':p['dependencies'].append(['i2','i1'])
            else:p['dependencies'].append(['out1','i2'])
            with self.assertRaises(DataError):self.check(p)
    def test_external_supply_channel_required(self):
        p=fixture();del p['information_nodes'][0]['supply_channel']
        with self.assertRaisesRegex(DataError,'schema'):self.check(p)
    def test_modality_linkage(self):
        p=fixture();p['information_nodes'][0]['modality_candidates'].append('image')
        with self.assertRaisesRegex(DataError,'missing_modality'):self.check(p)
        p['modality_hypotheses']=[{'node_id':'i1','supports_node_id':'i2','modality_candidate':'image','information_needed':'Spatial relation','modality_rationale':'Drawing needed','evidence_status':'unretrieved','necessity_status':'hypothesis'}]
        self.check(p)
        p['modality_hypotheses'][0]['evidence_status']='verified'
        with self.assertRaises(DataError):self.check(p)
    def test_internal_node_cannot_store_known_answer(self):
        p=fixture();p['information_nodes'][1]['answer']=42
        with self.assertRaisesRegex(DataError,'schema'):self.check(p)
    def test_inconsistent_review_cannot_admit(self):
        keys=['intent_preservation','deliverable_validity','information_sufficiency','dependency_correctness','minimality','multimodal_justification','case_neutrality']
        r={'accepted':True,'issues':[],'checks':dict.fromkeys(keys,True)};validate_review(r)
        r['checks']['intent_preservation']=False
        with self.assertRaisesRegex(DataError,'inconsistent'):validate_review(r)
        r.update(accepted=False,issues=['Intent drift']);validate_review(r)
    def test_actual_sample_matches_full_pool(self):
        rows=load_raw(Path(__file__).resolve().parents[2]/'work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl')
        self.assertEqual(len(rows),200)
    def test_zero_limit_writes_empty_output_without_model_call(self):
        repo=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp,patch('plan_intents.model_call') as model:
            root=Path(temp)
            report=run(repo/'work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl',root/'out',root/'cache',repo/'work-plans/config/blueprint_pilot.json',0,True)
            self.assertEqual(report['counts']['input'],0)
            self.assertEqual((root/'out/blueprints.jsonl').read_text(),'')
            model.assert_not_called()
if __name__=='__main__':unittest.main()
