"""Synthetic tool transcripts only; no API calls or search success claims."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from claude_search import analyze_trace, run_session
from search_provider import search


def message(kind, content):
    return {'type': kind, 'message': {'content': content}}


def transcript(result, name='WebSearch', is_error=False):
    return '\n'.join(json.dumps(r) for r in [
        {'type': 'system', 'subtype': 'init', 'tools': ['WebSearch','WebFetch'], 'model': 'fixture'},
        message('assistant', [{'type': 'tool_use', 'id': 't1', 'name': name, 'input': {'query': 'fixture'}}]),
        message('user', [{'type': 'tool_result', 'tool_use_id': 't1', 'is_error': is_error, 'content': result}])])


class ClaudeTraceTests(unittest.TestCase):
    def test_runtime_omits_limits_when_unset_and_preserves_explicit_limits(self):
        for bounded in (False,True):
            config={'model':'fixture','max_turns':6 if bounded else None,
                    'max_search_calls':2 if bounded else None,'timeout_seconds':30}
            process=MagicMock();process.communicate.return_value=('','');process.returncode=0
            with tempfile.TemporaryDirectory() as temp, patch('claude_search.subprocess.run',return_value=MagicMock(stdout='fixture-cli')), patch('claude_search.credentials',return_value=('https://example.org','fixture-not-a-real-key')), patch('claude_search.subprocess.Popen',return_value=process) as launch, patch.dict(os.environ,{'CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION':'1'}):
                run_session('fixture prompt',config,Path(temp))
                command=launch.call_args.args[0];env=launch.call_args.kwargs['env']
                self.assertEqual('--max-turns' in command,bounded)
                self.assertEqual('CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION' in env,bounded)
                if bounded:
                    self.assertEqual(command[command.index('--max-turns')+1],'6')
                    self.assertEqual(env['CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION'],'2')

    def test_only_actual_tool_links_become_candidates(self):
        text = 'Web search results\n\nLinks: [{"title":"Fixture","url":"https://example.org/data.csv"}]\n\nsummary'
        r = analyze_trace(transcript(text))
        self.assertEqual(r['websearch_calls'], 1)
        self.assertEqual(r['candidates'][0]['url'], 'https://example.org/data.csv')
        self.assertEqual(r['candidates'][0]['discovered_by_tool_use_id'], 't1')
    def test_assistant_claimed_search_is_not_evidence(self):
        text = json.dumps(message('assistant', [{'type':'text','text':'I searched: https://example.org/data.csv\nLinks: [{"url":"https://example.org/data.csv"}]'}]))
        r = analyze_trace(text)
        self.assertEqual(r['websearch_calls'], 0); self.assertEqual(r['candidates'], [])
    def test_errors_or_malformed_results_cannot_produce_candidates(self):
        for content, error in [('Links: [{"url":"https://example.org/"}]',True), ('Links: not-json',False), ('tool not available',False), ('Links: [{"url":"http://127.0.0.1/private"}]',False)]:
            self.assertEqual(analyze_trace(transcript(content,is_error=error))['candidates'], [])
    def test_fetch_404_even_without_error_flag_is_failure(self):
        r = analyze_trace(transcript('The server returned HTTP 404 Not Found. The response body was not retrieved.', name='WebFetch'))
        self.assertEqual(r['webfetch_calls'], 1)
        self.assertEqual(r['tool_results'][0]['page_access_status'], 'reported_failure')
        self.assertEqual(r['candidates'], [])
    def test_orphan_result_not_trusted(self):
        text = json.dumps(message('user', [{'type':'tool_result','tool_use_id':'missing','content':'Links: [{"url":"https://example.org/"}]'}]))
        self.assertEqual(analyze_trace(text)['candidates'], [])
    def test_missing_runtime_is_awaiting_search(self):
        with tempfile.TemporaryDirectory() as temp, patch('claude_search.available',return_value=False), patch('claude_search.search_query') as call:
            r=search('fixture',{'provider':'claude_code'},Path(temp))
            self.assertEqual(r['status'],'awaiting_search');call.assert_not_called()
    def test_provider_routes_and_replays_without_subprocess(self):
        receipt={'provider':'claude_code','query':'fixture','status':'searched','results':[],'search_api_called':True}
        with tempfile.TemporaryDirectory() as temp, patch('claude_search.available',return_value=True), patch('claude_search.search_query',return_value=receipt) as call:
            config={'provider':'claude_code','model':'fixture'}
            self.assertEqual(search('fixture',config,Path(temp)),receipt)
            self.assertEqual(search('fixture',config,Path(temp),True),receipt)
            self.assertEqual(call.call_count,1)


if __name__ == '__main__':unittest.main()
