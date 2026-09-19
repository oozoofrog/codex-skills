from __future__ import annotations
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'jev-workbench'
SPEC = importlib.util.spec_from_file_location('jev_kit', CORE/'scripts/jev_cli.py')
kit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kit)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packet = kit.read_json(CORE/'templates/plan-choice.json')
        self.response = kit.read_json(CORE/'fixtures/plan-choice.response.json')

    def prepared(self, packet=None, watch=None):
        source = self.root/'input.json'
        source.write_text(json.dumps(packet or self.packet))
        out = self.root/'run'
        kit.prepare(source, out, self.root, watch or [])
        return out

    def test_all_twelve_templates_and_fixtures_validate(self):
        paths = list((CORE/'templates').glob('*.json'))
        self.assertEqual(len(paths),12)
        for path in paths:
            with self.subTest(workflow=path.stem):
                packet=kit.read_json(path)
                kit.validate_packet(packet)
                kit.validate_response(packet['request'],kit.read_json(CORE/'fixtures'/f'{path.stem}.response.json'))

    def test_all_twelve_fixture_workflows_execute(self):
        for path in sorted((CORE/'templates').glob('*.json')):
            with self.subTest(workflow=path.stem):
                out=self.root/path.stem
                kit.prepare(path,out,self.root,[])
                result=kit.run(out,False,CORE/'fixtures'/f'{path.stem}.response.json',None,30)
                self.assertEqual(result['receipt']['origin'],'fixture')
                self.assertFalse(result['receipt']['eligible_for_delegated_followup'])
                self.assertFalse(result['receipt']['execution_authorized'])

    def test_json_duplicate_key_rejected(self):
        with self.assertRaises(kit.KitError):kit.loads('{"x":1,"x":2}')

    def test_nonfinite_json_rejected(self):
        for val in ['NaN','Infinity','-Infinity']:
            with self.subTest(value=val),self.assertRaises(kit.KitError):kit.loads('{"x":'+val+'}')

    def test_utf8_failure_rejected(self):
        with self.assertRaises(kit.KitError):kit.loads(b'\xff')

    def test_missing_packet_fields_rejected(self):
        del self.packet['authority']
        with self.assertRaises(kit.KitError):kit.validate_packet(self.packet)

    def test_unexpected_packet_fields_rejected(self):
        self.packet['automatic_execution']=True
        with self.assertRaises(kit.KitError):kit.validate_packet(self.packet)

    def test_boolean_schema_version_rejected(self):
        self.packet['schema_version']=True
        with self.assertRaises(kit.KitError):kit.validate_packet(self.packet)

    def test_choice_requires_abstention_for_delegation(self):
        del self.packet['request']['questions']['decision']['criteria']['NEEDS_EVIDENCE']
        with self.assertRaises(kit.KitError):kit.validate_packet(self.packet)

    def test_advisory_score_cannot_become_delegated(self):
        p=kit.read_json(CORE/'templates/review-signal.json');p['authority']='delegated'
        p['policy']['decision_question']='change_scope'
        with self.assertRaises(kit.KitError):kit.validate_packet(p)

    def test_api_unknown_field_rejected(self):
        self.packet['request']['temperature']=0
        with self.assertRaises(kit.KitError):kit.validate_packet(self.packet)

    def test_choice_missing_answers_rejected(self):
        self.response['answers']={}
        with self.assertRaises(kit.KitError):kit.validate_response(self.packet['request'],self.response)

    def test_choice_outside_candidates_rejected(self):
        self.response['answers']['decision']['choice']='invented'
        with self.assertRaises(kit.KitError):kit.validate_response(self.packet['request'],self.response)

    def test_choice_not_highest_probability_rejected(self):
        self.response['answers']['decision']['choice']='new_adapter'
        with self.assertRaises(kit.KitError):kit.validate_response(self.packet['request'],self.response)

    def test_probability_sum_rejected(self):
        self.response['answers']['decision']['probabilities']['local_handler']=0.2
        with self.assertRaises(kit.KitError):kit.validate_response(self.packet['request'],self.response)

    def test_boolean_confidence_rejected(self):
        self.response['answers']['decision']['confidence']=True
        with self.assertRaises(kit.KitError):kit.validate_response(self.packet['request'],self.response)

    def test_pinned_model_mismatch_rejected(self):
        self.response['model']='jev-other'
        with self.assertRaises(kit.KitError):kit.validate_response(self.packet['request'],self.response)

    def test_latest_alias_allows_returned_actual_model(self):
        self.packet['request']['model']='jev-latest'
        kit.validate_response(self.packet['request'],self.response)

    def test_negative_usage_rejected(self):
        self.response['usage']['input_tokens']=-1
        with self.assertRaises(kit.KitError):kit.validate_response(self.packet['request'],self.response)

    def test_score_mean_mismatch_rejected(self):
        p=kit.read_json(CORE/'templates/context-rank.json')
        r=kit.read_json(CORE/'fixtures/context-rank.response.json')
        r['answers']['relevance_d1']['score']=0
        with self.assertRaises(kit.KitError):kit.validate_response(p['request'],r)

    def test_score_legend_mismatch_rejected(self):
        p=kit.read_json(CORE/'templates/context-rank.json')
        r=kit.read_json(CORE/'fixtures/context-rank.response.json')
        r['answers']['relevance_d1']['legend']['0']='Changed rubric'
        with self.assertRaises(kit.KitError):kit.validate_response(p['request'],r)

    def test_noul_out_of_range_rejected(self):
        p=kit.read_json(CORE/'templates/issue-triage.json')
        r=kit.read_json(CORE/'fixtures/issue-triage.response.json')
        r['answers']['mentions_reconnect']['noul']=1.1
        with self.assertRaises(kit.KitError):kit.validate_response(p['request'],r)

    def test_possible_secrets_rejected(self):
        for value in ['-----BEGIN PRIVATE KEY-----','sk-'+'a'*30]:
            with self.subTest(value=value),self.assertRaises(kit.KitError):kit.secret_scan({'text':value})

    def test_sensitive_named_field_rejected(self):
        with self.assertRaises(kit.KitError):kit.secret_scan({'api_key':'abcd12345'})

    def test_byte_budget_rejected(self):
        self.packet['request']['state']={'text':'가'*100000}
        with self.assertRaises(kit.KitError):kit.validate_packet(self.packet)

    def test_prepare_does_not_upload_watched_file_contents(self):
        (self.root/'a.swift').write_text('LOCAL_ONLY_TEXT')
        out=self.prepared(watch=['a.swift'])
        self.assertNotIn('LOCAL_ONLY_TEXT',(out/'payload.json').read_text())
        self.assertEqual(len(kit.read_json(out/'manifest.json')['watched']),1)

    def test_prepare_refuses_overwrite(self):
        self.prepared()
        with self.assertRaises(kit.KitError):kit.prepare(self.root/'input.json',self.root/'run',self.root,[])

    def test_watched_file_changes_stale(self):
        (self.root/'a.swift').write_text('old')
        out=self.prepared(watch=['a.swift'])
        (self.root/'a.swift').write_text('new')
        self.assertFalse(kit.status(out)['fresh'])
        with self.assertRaises(kit.KitError):kit.inspect_run(out)

    def test_path_traversal_rejected(self):
        with self.assertRaises(kit.KitError):kit.hash_watched(self.root,['../outside'])

    def test_symlink_watch_rejected(self):
        (self.root/'a').write_text('data');(self.root/'link').symlink_to(self.root/'a')
        with self.assertRaises(kit.KitError):kit.hash_watched(self.root,['link'])

    def test_payload_tampering_rejected(self):
        out=self.prepared();payload=kit.read_json(out/'payload.json');payload['state']={'changed':'state'}
        (out/'payload.json').write_text(json.dumps(payload))
        with self.assertRaises(kit.KitError):kit.inspect_run(out)

    def test_fixture_cannot_authorize_followup(self):
        out=self.prepared()
        kit.run(out,False,CORE/'fixtures/plan-choice.response.json',None,30)
        with self.assertRaises(kit.KitError):kit.status(out,True)

    def test_cached_fixture_no_second_request(self):
        out=self.prepared();fixture=CORE/'fixtures/plan-choice.response.json'
        kit.run(out,False,fixture,None,30)
        self.assertEqual(kit.run(out,False,fixture,None,30)['status'],'CACHED')

    def test_cannot_promote_fixture_to_live(self):
        out=self.prepared();kit.run(out,False,CORE/'fixtures/plan-choice.response.json',None,30)
        with self.assertRaises(kit.KitError):kit.run(out,True,None,'whatever',30)

    def test_example_blocks_live_before_network(self):
        out=self.prepared()
        with mock.patch.object(kit,'live_request') as network:
            with self.assertRaises(kit.KitError):kit.run(out,True,None,None,30)
            network.assert_not_called()

    def test_real_input_requires_exact_approval_hash(self):
        self.packet['is_example']=False;out=self.prepared()
        with mock.patch.object(kit,'live_request') as network:
            with self.assertRaises(kit.KitError):kit.run(out,True,None,'wrong',30)
            network.assert_not_called()

    def test_mocked_live_valid_flow(self):
        self.packet['is_example']=False;out=self.prepared()
        approval=kit.read_json(out/'manifest.json')['approval_sha256']
        with mock.patch.dict(os.environ,{'TYPESAFE_API_KEY':'unit-test-key'}),mock.patch.object(kit,'live_request',return_value=self.response) as network:
            r=kit.run(out,True,None,approval,30)
            self.assertTrue(r['receipt']['eligible_for_delegated_followup'])
            self.assertFalse(r['receipt']['execution_authorized'])
            self.assertTrue(kit.status(out,True)['fresh'])
            kit.run(out,True,None,approval,30)
            network.assert_called_once()

    def test_low_confidence_is_review_not_other_choice(self):
        self.packet['policy']['min_confidence']=0.8
        r=kit.build_receipt(self.packet,self.response,'live')
        self.assertEqual(r['selected'],'local_handler')
        self.assertEqual(r['decision_status'],'NEEDS_REVIEW')
        self.assertFalse(r['eligible_for_delegated_followup'])

    def test_abstention_is_normal_decision(self):
        q=self.response['answers']['decision'];q['choice']='NEEDS_EVIDENCE'
        q['probabilities']={k:0.1 for k in q['probabilities']};q['probabilities']['NEEDS_EVIDENCE']=0.7
        kit.validate_response(self.packet['request'],self.response)
        r=kit.build_receipt(self.packet,self.response,'live')
        self.assertEqual(r['decision_status'],'NEEDS_EVIDENCE')

    def test_external_provenance_cannot_authorize(self):
        self.packet['is_example']=False;out=self.prepared()
        r=kit.run(out,False,None,None,30,external=CORE/'fixtures/plan-choice.response.json')
        self.assertEqual(r['receipt']['origin'],'external')
        self.assertFalse(r['receipt']['eligible_for_delegated_followup'])

    def test_delivery_unknown_is_not_replayed(self):
        out=self.prepared();kit.write_new(out/'attempt.json',{'origin':'live'})
        self.assertEqual(kit.status(out)['status'],'DELIVERY_UNKNOWN')
        with self.assertRaises(kit.KitError):kit.run(out,False,CORE/'fixtures/plan-choice.response.json',None,30)

    def test_service_failure_not_success_and_no_second_attempt(self):
        self.packet['is_example']=False;out=self.prepared()
        approval=kit.read_json(out/'manifest.json')['approval_sha256']
        with mock.patch.dict(os.environ,{'TYPESAFE_API_KEY':'unit-test-key'}),mock.patch.object(kit,'live_request',side_effect=kit.KitError('HTTP_529',4)) as network:
            with self.assertRaises(kit.KitError):kit.run(out,True,None,approval,30)
            self.assertEqual(kit.status(out)['failure']['status'],'UNAVAILABLE')
            with self.assertRaises(kit.KitError):kit.run(out,True,None,approval,30)
            network.assert_called_once()

    def test_redirect_blocked(self):
        with self.assertRaises(kit.KitError):kit.NoRedirect().redirect_request(None,None,302,'',{},'https://example.invalid')

    def test_lineage_requires_hash_and_reason(self):
        self.packet['lineage']={'parent_packet_sha256':'bad','change_reason':'new log'}
        with self.assertRaises(kit.KitError):kit.validate_packet(self.packet)
        self.packet['lineage']={'parent_packet_sha256':'a'*64,'change_reason':'new observation supplied'}
        kit.validate_packet(self.packet)

    def test_receipt_tampering_rejected(self):
        out=self.prepared();kit.run(out,False,CORE/'fixtures/plan-choice.response.json',None,30)
        receipt=kit.read_json(out/'receipt.json');receipt['execution_authorized']=True
        (out/'receipt.json').write_text(json.dumps(receipt))
        with self.assertRaises(kit.KitError):kit.status(out)

    def test_evaluation_reports_intentional_one_of_two(self):
        result=kit.evaluate(CORE/'fixtures/eval-cases.json')
        self.assertEqual((result['accepted'],result['total']),(1,2))
        self.assertFalse(result['execution_authorized'])

    def test_http_wire_uses_fixed_host_body_and_header(self):
        opener=mock.MagicMock()
        response_context=mock.MagicMock()
        response_context.__enter__.return_value.read.return_value=kit.canonical(self.response)
        opener.open.return_value=response_context
        with mock.patch.dict(os.environ,{'TYPESAFE_API_KEY':'unit-wire-key'}),mock.patch.object(kit.urllib.request,'build_opener',return_value=opener):
            output=kit.live_request(self.packet['request'],10)
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url,kit.ENDPOINT)
        self.assertEqual(request.get_header('Authorization'),'Bearer unit-wire-key')
        self.assertEqual(kit.loads(request.data),self.packet['request'])
        self.assertEqual(output,self.response)

    def test_http_error_does_not_echo_private_body(self):
        opener=mock.MagicMock()
        opener.open.side_effect=kit.urllib.error.HTTPError(kit.ENDPOINT,401,'Private text',{},None)
        with mock.patch.dict(os.environ,{'TYPESAFE_API_KEY':'unit-wire-key'}),mock.patch.object(kit.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(kit.KitError) as error:kit.live_request(self.packet['request'],10)
        self.assertIn('HTTP_401',str(error.exception))
        self.assertNotIn('Private text',str(error.exception))

    def test_transport_error_marks_delivery_unknown(self):
        opener=mock.MagicMock()
        opener.open.side_effect=kit.urllib.error.URLError('private diagnostic')
        with mock.patch.dict(os.environ,{'TYPESAFE_API_KEY':'unit-wire-key'}),mock.patch.object(kit.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(kit.KitError) as error:kit.live_request(self.packet['request'],10)
        self.assertIn('DELIVERY_UNKNOWN',str(error.exception))
        self.assertNotIn('private diagnostic',str(error.exception))

    def test_doctor_no_network_no_key_disclosure(self):
        env={**os.environ,'TYPESAFE_API_KEY':'DO-NOT-PRINT-THIS'}
        result=subprocess.run([sys.executable,str(CORE/'scripts/jev_cli.py'),'doctor'],capture_output=True,text=True,env=env,timeout=5)
        self.assertEqual(result.returncode,0)
        self.assertNotIn('DO-NOT-PRINT-THIS',result.stdout)
        self.assertFalse(json.loads(result.stdout)['network_called'])


if __name__=='__main__':unittest.main()
