"""Structure compilation never repairs professional meaning or fabricates prerequisites."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compile_blueprint import compile_blueprint, VOCABULARY
from plan_intents import validate_blueprint, DataError


def semantic():
    return {'objective':'Compare recorded amounts with the requested baseline.',
            'deliverable':{'kind':'report','description':'Comparison of amounts','preferred_formats':['md','pdf'],'requires':['compare']},
            'inputs':[{'name':'recorded','kind':'table','source':'workspace','description':'Recorded amounts','preferred_formats':['csv','xlsx']},
                      {'name':'baseline','kind':'table','source':'workspace','description':'Baseline amounts','preferred_formats':['xlsx']}],
            'operations':[{'name':'compare','type':'derived_information','description':'Differences between the source amounts','requires':['recorded','baseline']}]}


def compile_check(value):
    graph=compile_blueprint(value,'fixture');validate_blueprint(graph,{'seed_id':'fixture'});return graph


class CompilerTests(unittest.TestCase):
    def test_exact_edges_ids_and_no_input_mutation(self):
        value=semantic();original=copy.deepcopy(value);a=compile_check(value)
        self.assertEqual(a,compile_check(value));self.assertEqual(value,original)
        self.assertEqual(a['dependencies'],[['i1','i3'],['i2','i3'],['i3','out1']])
        self.assertTrue(all(n['critical'] for n in a['information_nodes'][:2]))
        self.assertEqual(a['modality_hypotheses'],[])
    def test_missing_reference_never_filled(self):
        value=semantic();value['operations'][0]['requires'].append('policy')
        with self.assertRaisesRegex(DataError,'unknown_requirement'):compile_check(value)
    def test_missing_professional_premise_is_not_invented(self):
        value=semantic();value['inputs'].pop();value['operations'][0]['requires']=['recorded']
        graph=compile_check(value)
        self.assertEqual(len(graph['information_nodes']),2)
        self.assertNotIn('Baseline amounts',[n['description'] for n in graph['information_nodes']])
        # This passes structural checks, but remains subject to independent semantic rejection.
    def test_output_dependencies_are_explicit(self):
        value=semantic();del value['deliverable']['requires']
        with self.assertRaises(DataError):compile_check(value)
    def test_duplicate_names_cycles_and_unused_nodes(self):
        for case in ('duplicate','cycle','unused'):
            value=semantic()
            if case=='duplicate':value['inputs'][1]['name']='recorded'
            elif case=='cycle':value['operations'][0]['requires'].append('compare')
            else:value['operations'][0]['requires']=['recorded']
            with self.assertRaises(DataError):compile_check(value)
    def test_direct_answer_can_have_complex_operations(self):
        value=semantic();value['deliverable'].update(kind='direct_answer',preferred_formats=[])
        graph=compile_check(value)
        self.assertEqual(len(graph['information_nodes']),3)
        self.assertEqual(graph['deliverables'][0]['preferred_formats'],[])
    def test_direct_text_only_empty_formats(self):
        value={'objective':'Respond to the specified professional request.',
               'deliverable':{'kind':'direct_answer','description':'Response','preferred_formats':[],'requires':['request']},
               'inputs':[{'name':'request','kind':'text_instruction','source':'task_instruction','description':'User request','preferred_formats':[]}],
               'operations':[]}
        compile_check(value)
        value['inputs'][0]['preferred_formats']=['txt']
        with self.assertRaises(DataError):compile_check(value)
    def test_bad_formats_and_media_rejected(self):
        for kind,formats in [('report',[]),('report',['xlsx']),('report',['mp4']),('media',['wav'])]:
            value=semantic();value['deliverable'].update(kind=kind,preferred_formats=formats)
            with self.assertRaises(DataError):compile_check(value)
    def test_formats_do_not_imply_visual_dependency(self):
        value=semantic();value['inputs'][0].update(kind='diagram',preferred_formats=['pdf','png'])
        graph=compile_check(value)
        self.assertEqual(graph['information_nodes'][0]['modality_candidates'],[])
        self.assertEqual(graph['modality_hypotheses'],[])
    def test_visual_dependency_links_to_actual_operation(self):
        value=semantic();value['inputs'][0].update(kind='diagram',preferred_formats=['svg','pdf'],modality_dependency={'modality':'visual_spatial','information_needed':'Relative component positions','required_operation':'Interpret component positions before comparing configurations','supports':'compare'})
        graph=compile_check(value);h=graph['modality_hypotheses'][0]
        self.assertEqual((h['node_id'],h['supports_node_id']),('i1','i3'))
        self.assertEqual(h['evidence_status'],'unretrieved')
        value['inputs'][0]['modality_dependency']['supports']='invented'
        with self.assertRaises(DataError):compile_check(value)
    def test_supported_vocabulary_contains_tex_and_no_media(self):
        self.assertIn('tex',VOCABULARY['inputs']['document'])
        self.assertIn('txt',VOCABULARY['deliverables']['report'])
        self.assertNotIn('audio',VOCABULARY['inputs'])
        self.assertNotIn('video',VOCABULARY['inputs'])


if __name__=='__main__':unittest.main()
