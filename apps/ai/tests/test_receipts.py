import json
import subprocess
import shutil
from io import BytesIO
from unittest.mock import patch
from unittest import skipUnless

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image, ImageDraw, ImageFont

from apps.ai.services import parse_receipt, receipt_draft
from apps.accounts.models import User
from apps.activity.models import Activity
from apps.expenses.models import Expense, ExpenseItem
from apps.expenses.services import create_expense, update_expense, delete_expense, equal_shares, snapshot
from apps.groups.services import create_group, add_member
from apps.settlements.services import balance_mismatches


class ExtractionTests(SimpleTestCase):
    def test_noisy_receipt_table_and_decorated_total(self):
        text = '''Be Se piere Sah cee ae
oS a ae
a Flame Kitchen Se ae
ee Restaurant es re aE
SSS 177-6, Tenkasi - Madurai Rd, ee ge
Se ag eee Maharaj Nagar, a
= Kadayanallur, Tamil Nadu a ee
—— Contact No: 00000000000 Pee 2
SS — 21 May 2025 02:01 PM SS eee
# Quick Bill ae Sai
y Bill No:22 ge
Quick Bill: 22 ee
Eee O ewe eee ee meee SSS
“% Quick Bill ee
3 Pay Mode: Cash Se
££ ftem Qty Rate Total _—
—- L.Ghee Rice 2 90 180 SS SSS
P= — 2.Beef Fry 1 100 100 ————————
3.Milk Peda 1 10 10 ——
=a Total Qty: Total Amount: Rs ————
ss 4 290.00 eS
a Grand Total : Rs 290.00 = =
aes eer eer SSS
Riss Scan & pay through any UP app — oS'''
        draft = receipt_draft(text)
        self.assertEqual([(row['name'], row['amount']) for row in draft['items']],
                         [('Ghee Rice', '180.00'), ('Beef Fry', '100.00'), ('Milk Peda', '10.00')])
        self.assertEqual(draft['amount'], '290.00')
        self.assertFalse(any('do not match' in warning for warning in draft['warnings']))

    @skipUnless(shutil.which('tesseract'), 'Tesseract binary is exercised in Docker.')
    def test_actual_tesseract_extracts_receipt_image(self):
        image = Image.new('RGB', (1000, 500), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=36)
        draw.multiline_text((40, 40), 'CAFE RECEIPT\nMeal    200.00\nTea      50.00\nTax      10.00\nTotal   260.00', font=font, fill='black', spacing=20)
        buffer = BytesIO(); image.save(buffer, 'PNG')
        draft = parse_receipt(SimpleUploadedFile('receipt.png', buffer.getvalue()))
        self.assertEqual(draft['amount'], '260.00', draft['text'])
        self.assertEqual([row['amount'] for row in draft['items']], ['200.00', '50.00', '10.00'], draft['text'])

    def test_draft_extracts_charges_ignores_subtotal_and_keeps_total(self):
        draft = receipt_draft('Cafe\nPizza 200.00\nTea 50.00\nSubtotal 250.00\nCGST 12.50\nService 10.00\nDiscount 5.00\nTOTAL 267.50\nCash 300.00\nChange 32.50')
        self.assertEqual(draft['amount'], '267.50')
        self.assertEqual([row['kind'] for row in draft['items']], ['item', 'item', 'tax', 'service', 'discount'])
        self.assertEqual(draft['items'][-1]['amount'], '-5.00')

    def test_integer_prices_currency_suffix_and_table_columns(self):
        draft = receipt_draft('CAFE\nBill No 123\nPhone 9876543210\nPaneer 2 100 200\nTea Rs. 50\nTax 12.5 INR\nGrand Total : 262.50 INR\nCash 300\nTotal Qty 3')
        self.assertEqual([row['amount'] for row in draft['items']], ['200.00', '50.00', '12.50'])
        self.assertEqual(draft['amount'], '262.50')

    def test_grouped_prices_and_product_names_containing_cash(self):
        draft = receipt_draft('Cashew Curry 1,200.00\nRice 200\nTotal 1,400.00')
        self.assertEqual([row['amount'] for row in draft['items']], ['1200.00', '200.00'])

    def test_empty_and_mismatched_extraction_warn_instead_of_claiming_success(self):
        self.assertIn('No receipt items', receipt_draft('Cafe\nTotal 200')['warnings'][0])
        self.assertIn('No readable text', receipt_draft('')['warnings'][0])
        self.assertIn('do not match', receipt_draft('Tea 50\nTotal 100')['warnings'][0])

    def image(self):
        data = BytesIO(); Image.new('RGB', (200, 100), 'white').save(data, 'PNG')
        return SimpleUploadedFile('receipt.png', data.getvalue())

    @patch('apps.ai.services.subprocess.run')
    def test_image_bytes_use_stdin_and_no_files(self, run):
        run.return_value.stdout = b'Tea 10.00\nTotal 10.00'
        self.assertEqual(parse_receipt(self.image())['amount'], '10.00')
        self.assertEqual(run.call_args.args[0][:3], ['tesseract', 'stdin', 'stdout'])
        self.assertTrue(run.call_args.kwargs['input'].startswith(b'\x89PNG'))
        self.assertEqual(run.call_args.kwargs['timeout'], 25)

    @patch('apps.ai.services.subprocess.run', side_effect=subprocess.TimeoutExpired('tesseract', 25))
    def test_timeout_is_safe_validation_error(self, run):
        with self.assertRaisesMessage(ValidationError, 'unavailable'):
            parse_receipt(self.image())

    def test_invalid_missing_and_oversize_uploads(self):
        for upload in [None, SimpleUploadedFile('fake.png', b'not an image')]:
            with self.assertRaises(ValidationError): parse_receipt(upload)
        with override_settings(RECEIPT_MAX_BYTES=10), self.assertRaises(ValidationError):
            parse_receipt(self.image())
        with override_settings(RECEIPT_MAX_PIXELS=10), self.assertRaises(ValidationError):
            parse_receipt(self.image())


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ReceiptLedgerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a, cls.b, cls.c, cls.outsider = [User.objects.create_user(username=name, email=f'{name}@example.com') for name in ['alice', 'bob', 'chris', 'outsider']]
        cls.group = create_group(actor=cls.a, name='Dinner')
        for user in [cls.b, cls.c]: add_member(actor=cls.a, group_id=cls.group.id, user_id=user.id)

    def values(self):
        return dict(paid_by=self.a.id, amount='12.01', description='Cafe', source='ocr', split_mode='itemised',
                    participants=[self.a.id, self.b.id, self.c.id], items=[
                        {'kind': 'item', 'name': 'Meal', 'amount': '9.00', 'payees': [self.b.id]},
                        {'kind': 'item', 'name': 'Tea', 'amount': '3.00', 'payees': [self.c.id]},
                        {'kind': 'tax', 'name': 'Tax', 'amount': '0.03'},
                        {'kind': 'discount', 'name': 'Discount', 'amount': '-0.02'}])

    def create(self, **changes):
        values = self.values(); values.update(changes)
        return create_expense(actor=self.a, group_id=self.group.id, **values)

    def test_equal_charges_item_assignment_and_integrity(self):
        expense = self.create()
        self.assertEqual(equal_shares(expense), {self.b.id: 901, self.c.id: 300})
        self.assertEqual(expense.items.count(), 4)
        self.assertEqual(Activity.objects.get(action='expense.created').after['items'], snapshot(expense)['items'])
        self.assertEqual(balance_mismatches(), [])

    def test_unassigned_shared_items_equal_bill_and_remainders(self):
        expense = self.create(amount='1.01', items=[{'kind': 'item', 'name': 'Shared', 'amount': '1.01'}])
        self.assertEqual(equal_shares(expense), {self.a.id: 34, self.b.id: 34, self.c.id: 33})
        expense = self.create(split_mode='equal')
        self.assertEqual(equal_shares(expense), {self.a.id: 401, self.b.id: 400, self.c.id: 400})
        self.assertEqual(balance_mismatches(), [])

    def test_invalid_receipts_leave_no_expense_items_or_balance_changes(self):
        for change in [dict(amount='99'), dict(paid_by=self.b.id), dict(items=[]), dict(source=[]),
                       dict(items=[{'kind': [], 'name': 'x', 'amount': '12.01'}]),
                       dict(items=[{'kind': 'item', 'name': 'x', 'amount': '12.01', 'payees': [self.outsider.id]}]),
                       dict(items=[{'kind': 'discount', 'name': 'x', 'amount': '12.01'}]),
                       dict(items=[{'kind': 'item', 'name': 'x', 'amount': '12.01', 'payees': [True]}]),
                       dict(items=[{'kind': 'tax', 'name': 'x', 'amount': '12.01'}])]:
            with self.subTest(change=change), self.assertRaises(ValidationError): self.create(**change)
        self.assertEqual(Expense.objects.count(), 0)
        self.assertEqual(ExpenseItem.objects.count(), 0)
        self.assertEqual(balance_mismatches(), [])

    def test_edit_delete_and_failed_edit_rollback(self):
        expense = self.create()
        before = snapshot(expense)
        with self.assertRaises(ValidationError): update_expense(actor=self.a, expense_id=expense.id, amount='90')
        expense.refresh_from_db(); self.assertEqual(snapshot(expense), before)
        expense = update_expense(actor=self.a, expense_id=expense.id, description='Corrected')
        self.assertEqual(snapshot(expense)['items'], before['items'])
        expense = update_expense(actor=self.a, expense_id=expense.id, participants=[self.b.id, self.c.id])
        self.assertEqual(expense.split_mode, 'itemised')
        self.assertEqual(equal_shares(expense), {self.b.id: 901, self.c.id: 300})
        expense = update_expense(actor=self.a, expense_id=expense.id, amount='2', items=[{'kind': 'item', 'name': 'Water', 'amount': '2', 'payees': [self.b.id]}])
        self.assertEqual(equal_shares(expense), {self.b.id: 200})
        self.assertEqual(balance_mismatches(), [])
        delete_expense(actor=self.a, expense_id=expense.id)
        self.assertEqual(expense.items.count(), 1)
        self.assertEqual(balance_mismatches(), [])

    @patch('apps.ai.views.parse_receipt')
    def test_parse_requires_membership_and_never_saves(self, parse):
        parse.return_value = receipt_draft('Tea 12.01\nTotal 12.01')
        path = f'/groups/{self.group.id}/receipts/parse'
        self.assertEqual(self.client.post(path).status_code, 401)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(path).status_code, 403)
        parse.assert_not_called()
        self.client.force_login(self.a)
        self.assertEqual(self.client.post(path).status_code, 200)
        self.assertEqual(Expense.objects.count(), 0)
        self.assertEqual(Activity.objects.filter(action='expense.created').count(), 0)
        self.assertEqual(self.client.get(f'/groups/{self.group.id}/receipts', HTTP_ACCEPT='text/html').status_code, 200)

    def test_approval_api_and_receipt_edit_screen(self):
        self.client.force_login(self.a)
        response = self.client.post('/expenses', json.dumps(dict(self.values(), group_id=self.group.id)), content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        pk = response.json()['id']
        detail = self.client.get(f'/expenses/{pk}').json()
        self.assertEqual(len(detail['items']), 4)
        self.assertEqual(detail['source'], 'ocr')
        self.assertContains(self.client.get(f'/expenses/{pk}', HTTP_ACCEPT='text/html'), 'Review and edit receipt')
        self.assertEqual(self.client.get(f'/groups/{self.group.id}/receipts?expense={pk}').status_code, 200)
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(f'/groups/{self.group.id}/receipts?expense={pk}').status_code, 403)

    def test_audit_failure_rolls_back_items_and_ledger(self):
        with patch('apps.expenses.services.record', side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError): self.create()
        self.assertFalse(Expense.objects.exists())
        self.assertFalse(ExpenseItem.objects.exists())
        self.assertEqual(balance_mismatches(), [])

    def test_csrf_and_streamed_upload_limit(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True); client.force_login(self.a)
        path = f'/groups/{self.group.id}/receipts/parse'
        self.assertEqual(client.post(path).status_code, 403)
        self.client.force_login(self.a)
        with override_settings(RECEIPT_MAX_BYTES=10):
            response = self.client.post(path, {'image': SimpleUploadedFile('too-big.png', b'x' * 100)})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Expense.objects.exists())
