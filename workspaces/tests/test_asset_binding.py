"""Small synthetic engineering fixtures, excluded from all live pilot statistics."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from common import DataError,sha256,json_bytes,save
from profile_files import parse_bytes,add_segment_ids
from asset_binding import compile_binding,binding_gaps,validate_review,assemble_case,model_handles
from asset_workspace import verify_asset_workspace


def fixture():
    p=parse_bytes(b'key,value\nreference,10\n','https://fixture.invalid/input.csv','text/csv');fid=p['file_id']
    plan={'seed_id':'synthetic_test_fixture','work_objective':'Compare source records.',
        'information_nodes':[{'id':'i1','type':'external_input','critical':True,'supply_channel':'workspace','modality_candidates':[]},
            {'id':'i2','type':'external_input','critical':True,'supply_channel':'task_instruction','modality_candidates':[]},
            {'id':'i3','type':'derived_information'}],
        'deliverables':[{'id':'out1'}],'dependencies':[['i1','i3'],['i2','i3'],['i3','out1']]}
    case={'case_title':'Synthetic test only','case_objective':'Compare records for the requested purpose.',
        'inputs':[{'node_id':'i1','status':'supported','instruction':None,'rationale':'Located fixture record',
            'references':[{'file_id':fid,'segment_id':p['segments'][0]['segment_id']}]},
            {'node_id':'i2','status':'supported','instruction':'Compare the available values.','rationale':'Hypothetical scope','references':[]}],
        'operations':[{'node_id':'i3','description':'Compare available source values.'}],
        'deliverables':[{'node_id':'out1','description':'Comparison report','format':'md'}],'limitations':[]}
    sources={fid:{'sha256':p['sha256'],'workspace_path':'workspace_init/references/input.csv'}}
    return plan,case,{fid:p},sources


class BindingTests(unittest.TestCase):
    def test_deterministic_binding_retains_source_location(self):
        plan,case,profiles,sources=fixture();g=compile_binding(case,plan,profiles,sources)
        self.assertEqual(g,compile_binding(case,plan,profiles,sources));self.assertEqual(binding_gaps(g,plan),[])
        self.assertEqual(g['bindings'][0]['references'][0]['locator'],'row:1')
        self.assertEqual(g['bindings'][1]['origin'],'synthetic_instruction')
        self.assertEqual(g['dependencies'],plan['dependencies'])
    def test_bad_refs_hashes_missing_operations_and_fake_facts(self):
        for mutation in ('unknown_file','unknown_segment','duplicate','hash','operation','fake_fact'):
            with self.subTest(mutation=mutation):
                plan,case,profiles,sources=fixture();ref=case['inputs'][0]['references'][0]
                if mutation=='unknown_file':ref['file_id']='invented'
                if mutation=='unknown_segment':ref['segment_id']='invented'
                if mutation=='duplicate':case['inputs'][0]['references'].append(copy.deepcopy(ref))
                if mutation=='hash':sources[ref['file_id']]['sha256']='bad'
                if mutation=='operation':case['operations']=[]
                if mutation=='fake_fact':case['inputs'][0]['instruction']='Invented actual sales are 50.'
                with self.assertRaises(DataError):compile_binding(case,plan,profiles,sources)
    def test_missing_input_remains_a_gap(self):
        plan,case,profiles,sources=fixture();case['inputs'][0]['status']='partial'
        self.assertEqual(binding_gaps(compile_binding(case,plan,profiles,sources),plan),['i1'])
    def test_visual_metadata_does_not_establish_content(self):
        plan,case,profiles,sources=fixture();plan['information_nodes'][0]['modality_candidates']=['image']
        with self.assertRaisesRegex(DataError,'visual_input_not_inspected'):compile_binding(case,plan,profiles,sources)
    def test_visual_observation_stays_unverified(self):
        plan,case,profiles,sources=fixture();plan['information_nodes'][0]['modality_candidates']=['image']
        p=next(iter(profiles.values()));p['segments']=[{'locator':'image:region:1','text':'A test mark','evidence_method':'model_visual_observation'}];add_segment_ids(p)
        case['inputs'][0]['references'][0]['segment_id']=p['segments'][0]['segment_id']
        g=compile_binding(case,plan,profiles,sources)
        self.assertEqual(g['bindings'][0]['references'][0]['verification_status'],'model_observation_unverified')
        plan['information_nodes'][0]['modality_candidates']=['audio']
        with self.assertRaisesRegex(DataError,'audio_content_not_inspected'):compile_binding(case,plan,profiles,sources)
    def test_reviewer_cannot_say_yes_with_failed_checks(self):
        review={'accepted':True,'checks':{k:True for k in ['intent_preservation','input_sufficiency','case_coherence','deliverable_appropriateness','no_answer_leakage','observation_boundaries']},'issues':[]}
        review['checks']['case_coherence']=False
        with self.assertRaisesRegex(DataError,'inconsistent_case_review'):validate_review(review)
    def test_input_hash_change_blocks_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);p,c,ps,ss=fixture();seed={'seed_id':p['seed_id']};(d/'workspace_init').mkdir()
            (d/'workspace_init/input.csv').write_text('changed')
            save(d/'construction/construction_report.json',{'seed_id':seed['seed_id'],'seed_sha256':sha256(json_bytes(seed)),
                'blueprint_sha256':sha256(json_bytes(p)),'construction_hashes':{},'workspace_files':{'input.csv':'original'},'status':'incomplete'})
            with self.assertRaisesRegex(DataError,'asset_workspace_changed'):verify_asset_workspace(d,p,seed)
    def test_compiler_only_defaults_non_applicable_instruction(self):
        plan,case,profiles,sources=fixture();del case['inputs'][0]['instruction']
        case['operations'][0]['rationale']='Extra model explanation, retained in raw receipt only.'
        normalized=assemble_case(case,plan);compile_binding(normalized,plan,profiles,sources)
        self.assertIsNone(normalized['inputs'][0]['instruction'])
        self.assertNotIn('rationale',normalized['operations'][0])
        del case['inputs'][1]['instruction']
        with self.assertRaisesRegex(DataError,'missing_instruction_value'):compile_binding(assemble_case(case,plan),plan,profiles,sources)
    def test_short_handles_recover_existing_ids_without_inventing_locations(self):
        plan,case,profiles,sources=fixture();views,_,decode=model_handles(profiles,sources)
        reference={'file_id':views[0]['file_id'],'segment_id':views[0]['segments'][0]['segment_id']}
        self.assertEqual(decode(reference),case['inputs'][0]['references'][0])
        self.assertEqual(decode({'file_id':'invented','segment_id':'invented'}),{'file_id':'invented','segment_id':'invented'})
    def test_commission_may_cite_a_source_without_becoming_a_source_fact(self):
        plan,case,profiles,sources=fixture();case['inputs'][1]['references']=copy.deepcopy(case['inputs'][0]['references'])
        g=compile_binding(case,plan,profiles,sources)
        self.assertEqual(g['bindings'][1]['origin'],'synthetic_instruction')


if __name__=='__main__':unittest.main()
