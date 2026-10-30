import json
import wave
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from openai import APIStatusError, APIConnectionError

import httpx
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, Client, override_settings

from apps.accounts.models import User
from apps.ai.services import VoiceUnavailable, parse_transcript, transcribe, validate_draft
from apps.expenses.models import Expense
from apps.expenses.services import equal_shares, update_expense, delete_expense
from apps.groups.services import create_group, add_member
from apps.settlements.services import balance_mismatches


def audio(seconds=1):
    buffer = BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000)
        output.writeframes(b'\0\0' * 16000 * seconds)
    return SimpleUploadedFile('voice.wav', buffer.getvalue(), 'audio/wav')


def draft(payer=1, participants=None):
    return dict(amount='600.01', description='Dinner', paid_by=payer,
                participants=participants or [1, 2], warnings=[])


@override_settings(SARVAM_API_KEYS=['first', 'second'], GROQ_API_KEYS=['test-only'])
class VoiceProviderTests(SimpleTestCase):
    def test_comma_separated_settings_ignore_whitespace_and_empty_entries(self):
        from config.settings import env_list
        for name in ['SARVAM_API_KEYS', 'GROQ_API_KEYS']:
            with self.subTest(name=name), patch.dict('os.environ', {name: ' first, ,second ,third, '}):
                self.assertEqual(env_list(name), ['first', 'second', 'third'])

    @patch('apps.ai.services.httpx.Client')
    def test_fallback_including_rate_limits_and_replayed_in_memory_audio(self, client):
        post = client.return_value.__enter__.return_value.post
        for code in [401, 402, 403, 429, 500, 503]:
            with self.subTest(code=code):
                post.reset_mock()
                post.side_effect = [httpx.Response(code), httpx.Response(200, json={'transcript': 'Maine dinner ke 600 diye'})]
                self.assertIn('600', transcribe(audio()))
                self.assertEqual(post.call_count, 2)
                self.assertEqual(post.call_args_list[0].kwargs['files'], post.call_args_list[1].kwargs['files'])
                self.assertEqual(post.call_args.kwargs['headers']['api-subscription-key'], 'second')
                self.assertEqual(post.call_args.kwargs['data']['mode'], 'codemix')

    @patch('apps.ai.services.httpx.Client')
    def test_transport_failure_falls_back_but_bad_audio_does_not(self, client):
        post = client.return_value.__enter__.return_value.post
        post.side_effect = [httpx.ConnectError('private details'), httpx.Response(200, json={'transcript': 'Dinner'})]
        self.assertEqual(transcribe(audio()), 'Dinner')
        post.reset_mock(); post.side_effect = None; post.return_value = httpx.Response(422)
        with self.assertRaises(ValidationError): transcribe(audio())
        self.assertEqual(post.call_count, 1)

    @patch('apps.ai.services.httpx.Client')
    def test_exhaustion_does_not_expose_provider_body_or_keys(self, client):
        client.return_value.__enter__.return_value.post.return_value = httpx.Response(403, text='secret body')
        with self.assertRaisesMessage(VoiceUnavailable, 'temporarily unavailable'): transcribe(audio())

    @patch('apps.ai.services.httpx.Client')
    def test_reject_oversized_long_truncated_and_invalid_audio_before_provider(self, client):
        for upload in [None, audio(31), SimpleUploadedFile('bad.wav', b'not audio'),
                       SimpleUploadedFile('truncated.wav', audio().read()[:-100]),
                       SimpleUploadedFile('huge.wav', b'x' * (2 * 1024 * 1024 + 1))]:
            with self.assertRaises(ValidationError): transcribe(upload)
        client.assert_not_called()

    @patch('apps.ai.services.OpenAI')
    def test_strict_schema_and_only_group_context_sent_to_groq(self, provider):
        completion = provider.return_value.__enter__.return_value.chat.completions.create
        completion.return_value = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(draft())))])
        result = parse_transcript('Maine 600.01 dinner par diye', [{'user_id': 1, 'user__username': 'a'}, {'user_id': 2, 'user__username': 'b'}], 1)
        self.assertEqual(result['source'], 'voice')
        self.assertEqual(result['amount'], '600.01')
        self.assertTrue(completion.call_args.kwargs['response_format']['json_schema']['strict'])
        self.assertNotIn('tools', completion.call_args.kwargs)
        self.assertEqual(provider.call_args.kwargs['max_retries'], 0)

    def test_untrusted_money_and_member_ids_are_validated(self):
        for amount in [12.2, 'NaN', '1.001', '-3', '0', '1e3', str(2**63)]:
            data = draft(); data['amount'] = amount
            with self.subTest(amount=amount), self.assertRaises(ValueError): validate_draft(data, {1, 2})
        result = validate_draft(draft(payer=99, participants=[True, 99]), {1, 2})
        self.assertIsNone(result['paid_by']); self.assertEqual(result['participants'], [])
        self.assertEqual(len(result['warnings']), 2)

    @override_settings(GROQ_API_KEYS=['first', 'second'])
    @patch('apps.ai.services.OpenAI')
    def test_groq_fallback_uses_keys_in_order(self, provider):
        completion = provider.return_value.__enter__.return_value.chat.completions.create
        success = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(draft())))])
        request = httpx.Request('POST', 'https://api.groq.com/openai/v1/chat/completions')
        failures = [APIStatusError('private details', response=httpx.Response(code, request=request), body=None)
                    for code in [401, 402, 403, 429, 500, 503]]
        failures.append(APIConnectionError(request=request))
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                provider.reset_mock()
                completion.side_effect = [failure, success]
                self.assertEqual(parse_transcript('Dinner', [{'user_id': 1}, {'user_id': 2}], 1)['amount'], '600.01')
                self.assertEqual([call.kwargs['api_key'] for call in provider.call_args_list], ['first', 'second'])

    @override_settings(GROQ_API_KEYS=['first', 'second'])
    @patch('apps.ai.services.OpenAI')
    def test_groq_invalid_requests_and_exhaustion_are_safe(self, provider):
        completion = provider.return_value.__enter__.return_value.chat.completions.create
        request = httpx.Request('POST', 'https://api.groq.com/openai/v1/chat/completions')
        for code, calls in [(400, 1), (429, 2)]:
            with self.subTest(code=code):
                provider.reset_mock()
                completion.side_effect = APIStatusError('secret body', response=httpx.Response(code, request=request), body=None)
                with self.assertRaisesMessage(VoiceUnavailable, 'Could not parse'):
                    parse_transcript('Dinner', [{'user_id': 1}], 1)
                self.assertEqual(provider.call_count, calls)

    @override_settings(SARVAM_API_KEYS=[], GROQ_API_KEYS=[])
    def test_missing_config_and_empty_transcript_have_actionable_errors(self):
        with self.assertRaisesMessage(VoiceUnavailable, 'not configured'): transcribe(audio())
        with self.assertRaisesMessage(VoiceUnavailable, 'not configured'): parse_transcript('Dinner', [], 1)
        with self.assertRaises(ValidationError): parse_transcript('', [], 1)


class VoiceWorkflowTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(username='speaker', email='speaker@example.com', password='abc')
        self.b = User.objects.create_user(username='friend', email='friend@example.com', password='abc')
        self.outsider = User.objects.create_user(username='outsider', email='outsider@example.com', password='abc')
        self.group = create_group(actor=self.a, name='Dinner')
        add_member(actor=self.a, group_id=self.group.id, user_id=self.b.id)
        self.url = f'/groups/{self.group.id}/voice'
        self.client.force_login(self.a)

    @patch('apps.ai.views.parse_transcript')
    @patch('apps.ai.views.transcribe', return_value='Dinner 600.01')
    def test_audio_and_typed_transcript_create_no_ledger_writes(self, speech, parser):
        parser.return_value = draft(self.a.id, [self.a.id, self.b.id])
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url + '/parse', {'audio': audio()}).status_code, 200)
        self.assertEqual(self.client.post(self.url + '/parse', {'transcript': 'Dinner 600.01'}, content_type='application/json').status_code, 200)
        self.assertEqual(Expense.objects.count(), 0)
        self.assertEqual(balance_mismatches(), [])

    def test_approval_is_required_then_saves_edited_fields_and_preserves_ledger(self):
        values = dict(paid_by=self.b.id, amount='10.01', description='Corrected tea', split_mode='equal', participants=[self.a.id, self.b.id])
        self.assertEqual(self.client.post(self.url + '/approve', values).status_code, 400)
        self.assertEqual(Expense.objects.count(), 0)
        values['approved'] = 'yes'
        self.assertEqual(self.client.post(self.url + '/approve', values).status_code, 302)
        expense = Expense.objects.get()
        self.assertEqual(expense.source, 'voice'); self.assertEqual(expense.paid_by_id, self.b.id)
        self.assertEqual(equal_shares(expense), {self.a.id: 501, self.b.id: 500})
        expense = update_expense(actor=self.a, expense_id=expense.id, amount='12.01')
        self.assertEqual(expense.source, 'voice'); self.assertEqual(balance_mismatches(), [])
        delete_expense(actor=self.a, expense_id=expense.id)
        self.assertEqual(balance_mismatches(), [])

    @patch('apps.ai.views.parse_transcript')
    def test_membership_and_csrf_are_checked_before_provider(self, parser):
        csrf_client = Client(enforce_csrf_checks=True); csrf_client.force_login(self.a)
        self.assertEqual(csrf_client.post(self.url + '/parse', {'transcript': 'Dinner'}).status_code, 403)
        self.client.force_login(self.outsider)
        for path in [self.url, self.url + '/parse', self.url + '/approve']:
            response = self.client.get(path) if path == self.url else self.client.post(path, {'transcript': 'Dinner'})
            self.assertEqual(response.status_code, 403)
        parser.assert_not_called()

    @patch('apps.ai.views.parse_transcript', side_effect=VoiceUnavailable('Parsing unavailable'))
    def test_transcript_survives_parser_failure(self, parser):
        response = self.client.post(self.url + '/parse', {'transcript': 'Dinner'}, content_type='application/json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['transcript'], 'Dinner')
        self.assertEqual(Expense.objects.count(), 0)
