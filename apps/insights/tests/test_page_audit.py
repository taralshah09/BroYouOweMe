from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.test import Client, TestCase, override_settings
from django.urls import resolve

from apps.accounts.models import User
from apps.expenses.services import create_expense, manage_category
from apps.groups.services import add_member, create_group, create_invite
from apps.settlements.services import create_settlement


class PageStructure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.labels, self.links, self.headings = [], [], [], []
        self.main_count = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.append(values["id"])
        if tag == "label" and "for" in values:
            self.labels.append(values["for"])
        if tag == "a" and "href" in values:
            self.links.append(values["href"])
        if tag == "form" and values.get("action"):
            self.links.append(values["action"])
        if tag == "h1":
            self.headings.append(tag)
        if tag == "main":
            self.main_count += 1


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class PageAuditTests(TestCase):
    def test_all_page_surfaces_render_with_landmarks_labels_and_valid_local_links(self):
        actor = User.objects.create_user(username="audit_owner", email="owner@example.invalid")
        friend = User.objects.create_user(username="audit_friend", email="friend@example.invalid")
        group = create_group(actor=actor, name="Audit trip")
        add_member(actor=actor, group_id=group.id, user_id=friend.id)
        expense = create_expense(actor=actor, group_id=group.id, paid_by=actor.id, amount="12.00", description="Dinner")
        manage_category(actor=actor, group_id=group.id, name="Coffee")
        create_settlement(actor=friend, group_id=group.id, receiver=actor.id, amount="1.00")
        invite = create_invite(actor=actor, group_id=group.id)
        self.client.force_login(actor)
        paths = ["/", "/groups", "/balances", f"/expenses/{expense.id}", f"/invite/{invite.token}"]
        paths += [f"/groups/{group.id}{suffix}" for suffix in ["", "/members", "/invites", "/expenses", "/balances", "/categories", "/receipts", "/voice", "/settlements", "/simplified", "/activity", "/insights", "/nudges"]]
        for path in paths + ["/signup", "/login", f"/groups/{group.id}/insights?month=invalid"]:
            with self.subTest(path=path):
                client = Client() if path in {"/signup", "/login"} else self.client
                response = client.get(path, HTTP_ACCEPT="text/html")
                self.assertEqual(response.status_code, 400 if "invalid" in path else 200)
                page = PageStructure()
                page.feed(response.content.decode())
                self.assertEqual(page.main_count, 1)
                self.assertEqual(len(page.headings), 1)
                self.assertEqual(len(page.ids), len(set(page.ids)), "Duplicate HTML IDs")
                self.assertFalse(set(page.labels) - set(page.ids), "Label points to a missing field")
                for link in page.links:
                    url = urlsplit(link)
                    if not url.scheme and not url.netloc and url.path.startswith("/"):
                        resolve(url.path)
                    if not url.scheme and not url.netloc and url.fragment and url.path in {"", urlsplit(path).path}:
                        self.assertIn(url.fragment, page.ids, "Link targets a missing section")

    def test_expense_and_balance_navigation_keep_the_current_group(self):
        actor = User.objects.create_user(username="nav_owner", email="nav@example.invalid")
        group = create_group(actor=actor, name="A very long group name for navigation")
        expense = create_expense(actor=actor, group_id=group.id, paid_by=actor.id,
                                 amount="12.00", description="Dinner")
        self.client.force_login(actor)
        for path in [f"/expenses/{expense.id}", f"/groups/{group.id}/balances"]:
            with self.subTest(path=path):
                response = self.client.get(path, HTTP_ACCEPT="text/html")
                page = PageStructure()
                page.feed(response.content.decode())
                self.assertIn(f"/groups/{group.id}#add-expense", page.links)
                self.assertIn(f"/groups/{group.id}/activity", page.links)
                self.assertNotContains(response, 'data-group-open="expense"')
        dashboard = self.client.get("/groups", HTTP_ACCEPT="text/html")
        self.assertContains(dashboard, 'data-group-open="expense"')
