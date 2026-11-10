import copy
import json
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from construct_seeds import (ROOT, DataError, pairs_for, make_seed, validate_links, validate_review,
                             seed_sample, llm_call, GENERATOR)
from sample_seeds import load_catalog, eligibility
from seed_evidence import Paragraphs, retrieve_pair, canonical_url, sha256


class ConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(ROOT / 'data/processed')
        decisions, _ = eligibility(cls.catalog, annotations=ROOT / 'data/annotations/ai4work_digital_task_annotation.xlsx')
        cls.pairs = pairs_for(cls.catalog, decisions)
        cls.vocab = json.loads((ROOT / 'config/execution_patterns.json').read_text())

    def setUp(self):
        self.pair = ('13-1023.00', '4.A.1.a.1.g.1')
        # Explicit test fixture, never written to production candidates or evidence.
        quote = 'Evaluate suppliers on the basis of the price, quality, and speed of delivery of their products and services'
        eid = 'ev_' + '1' * 24
        self.evidence = {eid: {'excerpt': quote, 'occupation_dwa_pairs': [list(self.pair)]}}
        self.proposal = {'source_task_ids': ['1144'], 'work_demand': 'Evaluate suppliers based on price, quality and delivery speed.',
                         'execution_pattern': 'evaluation_and_selection', 'input_file_families': ['reports'], 'evidence_ids': [eid]}
        self.seed = make_seed(self.proposal, self.pair, self.vocab)
        self.review = {'supported': True, 'case_neutral': True, 'occupational_fit': True, 'pattern_fit': True,
                       'input_families_fit': True, 'duplicate': False, 'rationale': 'Unit-test mocked review; not a model result.',
                       'claims': [{'claim': self.proposal['work_demand'], 'evidence_id': eid, 'quote': quote}]}

    def test_official_pair_membership_and_valid_schema(self):
        validate_links(self.seed, self.pairs, self.evidence, self.vocab)
        self.assertIn('1144', self.pairs[self.pair])
        validate_review(self.review, self.seed, self.evidence)

    def test_unknown_pattern_extra_fields_wrong_types_rejected(self):
        for key, value in [('execution_pattern', 'invented'), ('source_task_ids', '1144'),
                           ('input_file_families', ['not_real']), ('unexpected', True)]:
            obj = {**self.proposal, key: value}
            with self.assertRaises(DataError): make_seed(obj, self.pair, self.vocab)

    def test_cross_occupation_task_and_fake_evidence_rejected(self):
        for key, value in [('source_task_ids', ['3394']), ('evidence_ids', ['ev_' + '2' * 24])]:
            s = make_seed({**self.proposal, key: value}, self.pair, self.vocab)
            with self.assertRaises(DataError): validate_links(s, self.pairs, self.evidence, self.vocab)
        self.evidence[self.seed['evidence_ids'][0]]['occupation_dwa_pairs'] = []
        with self.assertRaises(DataError): validate_links(self.seed, self.pairs, self.evidence, self.vocab)

    def test_unsupported_demand_or_fabricated_quote_rejected(self):
        for field in ('supported', 'case_neutral', 'occupational_fit', 'pattern_fit', 'input_families_fit'):
            with self.assertRaises(DataError): validate_review({**self.review, field: False}, self.seed, self.evidence)
        with self.assertRaises(DataError): validate_review({**self.review, 'supported': 'true'}, self.seed, self.evidence)
        with self.assertRaises(DataError): validate_review({**self.review, 'duplicate': True}, self.seed, self.evidence)
        fake = copy.deepcopy(self.review); fake['claims'][0]['quote'] = 'This quotation does not occur in the retrieved evidence.'
        with self.assertRaises(DataError): validate_review(fake, self.seed, self.evidence)

    def test_greedy_reproducibility_caps_and_duplicates(self):
        seeds = [self.seed]
        for i, (pair, tids) in enumerate(list(self.pairs.items())[:8]):
            proposal = {**self.proposal, 'source_task_ids': tids[:1],
                        'work_demand': 'Test-only demand ' + self.catalog['tasks'][tids[0]]['task_text'],
                        'execution_pattern': list(self.vocab['patterns'])[i % 8]}
            seeds.append(make_seed(proposal, pair, self.vocab))
        weights = dict.fromkeys(['occupation', 'dwa', 'pattern', 'file_family'], 1)
        a, _ = seed_sample(seeds, 5, 42, weights, max_occupation=1)
        b, _ = seed_sample(list(reversed(seeds)), 5, 42, weights, max_occupation=1)
        self.assertEqual(a, b)
        selected = [s for s in seeds if s['seed_id'] in a]
        self.assertEqual(len(selected), len({s['occupation_code'] for s in selected}))
        with self.assertRaises(DataError): seed_sample(seeds, 1, 1, {**weights, 'occupation': float('nan')})

    def test_html_extraction_excludes_scripts_and_preserves_quotes(self):
        parser = Paragraphs()
        parser.feed('<script>invented evidence</script><p>Evaluate <b>suppliers</b> on the basis of price, quality, and delivery speed.</p>')
        self.assertEqual(parser.items, ['Evaluate suppliers on the basis of price, quality, and delivery speed.'])
        self.assertEqual(canonical_url('https://EXAMPLE.COM/page#x'), 'https://example.com/page')
        with self.assertRaises(DataError): canonical_url('file:///etc/passwd')

    def test_llm_request_configuration_and_response_cache(self):
        cfg = {'model': 'mock-test-model', 'endpoint': 'https://mock.invalid/chat/completions', 'parameters': {'temperature': 0}}
        with tempfile.TemporaryDirectory() as tmp, patch('construct_seeds.request_json') as request:
            request.return_value = {'model': 'mock-test-model', 'choices': [{'message': {'content': '```json\n{"seeds": []}\n```'}}]}
            first, metadata = llm_call(cfg, GENERATOR, {'test': True}, Path(tmp))
            second, metadata2 = llm_call(cfg, GENERATOR, {'test': True}, Path(tmp))
            self.assertEqual(first, second); self.assertEqual(metadata, metadata2)
            request.assert_called_once()
            self.assertEqual(metadata['model_requested'], cfg['model'])
            self.assertIn('generated_at', metadata)
            cfg['model'] = 'different-test-model'
            llm_call(cfg, GENERATOR, {'test': True}, Path(tmp))
            self.assertEqual(request.call_count, 2)

    def test_no_sources_does_not_invent_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'sources.json').write_text('{"sources": []}')
            evidence, status = retrieve_pair(self.pair, ['1144'], self.catalog,
                {'provider': 'url_manifest', 'manifest': 'sources.json'}, root, root / 'cache')
            self.assertEqual(evidence, []); self.assertEqual(status['reason'], 'no_source_urls')


if __name__ == '__main__': unittest.main()
