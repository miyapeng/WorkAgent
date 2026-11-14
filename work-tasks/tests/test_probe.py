"""Small deterministic fixtures; never counted as real pilot executions."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from probe_sandbox import runtime, writable, preflight, execute
from probe_evaluate import check_judge, mutations, report_numbers
from probe_reference import stats19
from run_probe import hashes


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.text='Collision data rows: 10.'
        self.rubric={'items':[{'rubric_id':'r1','verification_type':'semantic','weight':1}]}
        self.graph={'nodes':[{'evidence_id':'e1'}]}
        self.reference={'metrics':{'collision.rows':{'value':'10','unit':'records','absolute_tolerance':0}}}
        self.answer={'items':[{'rubric_id':'r1','score':1,'verdict':'passed','report_line_ids':['line_1'],'evidence_ids':['e1'],'reason':'Matches.'}],
            'numeric_claims':[{'metric_id':'collision.rows','report_number_id':'num_1_1'}], 'issues':[], 'limitations':['Synthetic fixture.']}
    def check(self,a=None,text=None):return check_judge(a or self.answer,text or self.text,self.rubric,self.graph,self.reference)
    def test_exact_comparison(self):self.assertTrue(self.check()['assisted_numeric_checks'][0]['passed'])
    def test_wrong_number(self):
        a=copy.deepcopy(self.answer);a['numeric_claims'][0].update(report_number_id='num_1_1')
        self.assertFalse(self.check(a,'Collision data rows: 11.')['full_credit_candidate'])
    def test_rounded_probability_sum(self):
        self.reference['metrics']['collision.rows'].update(value='10.4',unit='expected_records')
        self.assertTrue(self.check()['assisted_numeric_checks'][0]['passed'])
    def test_fifo_not_read(self):
        with tempfile.TemporaryDirectory() as d:
            os.mkfifo(Path(d)/'pipe')
            with self.assertRaises(ValueError):hashes(Path(d))
    def test_fabricated_quote(self):
        a=copy.deepcopy(self.answer);a['numeric_claims'][0]['report_number_id']='num_99_1'
        with self.assertRaises(ValueError):self.check(a)
    def test_invalid_evidence(self):
        a=copy.deepcopy(self.answer);a['items'][0]['evidence_ids']=['invented']
        with self.assertRaises(ValueError):self.check(a)
    def test_invalid_location(self):
        a=copy.deepcopy(self.answer);a['items'][0]['report_line_ids']=['line_99']
        with self.assertRaises(ValueError):self.check(a)
    def test_duplicate_rubric(self):
        a=copy.deepcopy(self.answer);a['items']*=2
        with self.assertRaises(ValueError):self.check(a)
    def test_no_score_for_unassessable(self):
        a=copy.deepcopy(self.answer);a['items'][0].update(verdict='unassessable',score=None)
        self.assertIsNone(self.check(a)['semantic_score'])
    def test_mutations_do_not_invent_positive(self):
        rows=mutations('No numeric result.',self.reference)
        self.assertNotIn('wrong_collision_count',[r['id'] for r in rows])
        self.assertEqual(len(rows),2)
    def test_number_ids_preserve_printed_values(self):
        values=report_numbers('Total 100,927. Estimate 27,273.9; missing −1.')
        self.assertEqual([v['literal'] for v in values.values()],['100,927','27,273.9','−1'])
    def test_zero_is_not_blank(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'dft-road-casualty-statistics-collision-2024.csv').write_text('collision_index,collision_year,number_of_vehicles,number_of_casualties,collision_severity,collision_adjusted_severity_serious,collision_adjusted_severity_slight\na,2024,1,1,1,0,0\n')
            (root/'dft-road-casualty-statistics-vehicle-2024.csv').write_text('collision_index,collision_year,vehicle_reference\na,2024,1\n')
            (root/'dft-road-casualty-statistics-casualty-2024.csv').write_text('collision_index,collision_year,vehicle_reference,casualty_reference\na,2024,1,1\n')
            m=stats19(root)['metrics']
            self.assertEqual(m['collision.collision_adjusted_severity_serious.fatal_empty']['value'],'0')
            self.assertEqual(m['collision.collision_adjusted_severity_serious.fatal_zero']['value'],'1')
    def test_counts_scope(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'dft-road-casualty-statistics-collision-2024.csv').write_text('collision_index,collision_year,number_of_vehicles,number_of_casualties\na,2024,1,1\n')
            (root/'dft-road-casualty-statistics-vehicle-2024.csv').write_text('collision_index,collision_year,vehicle_reference\na,2024,1\na,2024,1\n')
            (root/'dft-road-casualty-statistics-casualty-2024.csv').write_text('collision_index,collision_year,vehicle_reference,casualty_reference\nb,2024,1,1\n')
            m=stats19(root)['metrics']
            self.assertEqual(m['vehicle.duplicate_key_excess']['value'],'1')
            self.assertEqual(m['casualty.unmatched_collision']['value'],'1')
            self.assertEqual(m['collision.number_of_vehicles_mismatch']['value'],'1')
    def test_symlink_not_exported(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'escape').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):hashes(Path(d))


@unittest.skipUnless(os.geteuid()==0 and sys.platform=='linux','requires actual privileged Linux chroot')
class SandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)/'root'
        runtime(cls.root);(cls.root/'work/task.json').write_text('{"synthetic_test_fixture":true}')
        writable(cls.root)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_actual_isolation_and_parsers(self):self.assertEqual(preflight(self.root)['returncode'],0)
    def test_host_secret_and_env_unavailable(self):
        result=execute(self.root,"import os; assert not os.path.exists('/etc/passwd'); assert 'HOME' not in os.environ; print('ok')")
        self.assertEqual(result['returncode'],0)
    def test_input_readonly_and_output_persists(self):
        self.assertNotEqual(execute(self.root,"open('task.json','w').write('bad')")['returncode'],0)
        self.assertEqual(execute(self.root,"open('outputs/report.md','w').write('fixture')")['returncode'],0)
        self.assertEqual(execute(self.root,"print(open('outputs/report.md').read())")['stdout'].strip(),'fixture')
    def test_exec_and_socket_denied(self):
        self.assertNotEqual(execute(self.root,"import socket; socket.socket()")['returncode'],0)
        self.assertNotEqual(execute(self.root,"import os; os.execv('/runtime/bin/python',['python','-c','print(1)'])")['returncode'],0)
    def test_cpu_limit(self):self.assertNotEqual(execute(self.root,'while True: pass',timeout=1)['returncode'],0)


if __name__=='__main__':unittest.main()
