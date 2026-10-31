from django.urls import path

from apps.accounts import views as accounts
from apps.expenses import views as expenses
from apps.groups import views as groups
from apps.settlements import views as settlements
from apps.activity.views import activity
from apps.ai import views as ai
from apps.insights import views as insights
from apps.settlements.views import balances

urlpatterns = [
    path("groups/<int:group_id>/insights", insights.insights, name="insights"),
    path("groups/<int:group_id>/expenses/export.csv", insights.export_csv, name="expense-export"),
    path("groups/<int:group_id>/nudges", insights.nudges, name="nudges"),
    path("groups/<int:group_id>/voice", ai.voice_review, name="voice-review"),
    path("groups/<int:group_id>/voice/parse", ai.voice_parse, name="voice-parse"),
    path("groups/<int:group_id>/voice/approve", ai.voice_approve, name="voice-approve"),
    path("groups/<int:group_id>/receipts", ai.receipt_review, name="receipt-review"),
    path("groups/<int:group_id>/receipts/parse", ai.receipt_parse, name="receipt-parse"),
    path("", accounts.home, name="home"),
    path("health", accounts.health, name="health"),
    path("signup", accounts.signup, name="signup"),
    path("login", accounts.login, name="login"),
    path("logout", accounts.logout, name="logout"),
    path("invite/<str:token>", groups.invite_preview, name="invite-preview"),
    path("invite/<str:token>/join", groups.invite_join, name="invite-join"),
    path("groups/<int:group_id>/invites", groups.invites, name="invites"),
    path("groups/<int:group_id>/invites/<int:invite_id>", groups.invite_revoke, name="invite-revoke"),
    path("groups/<int:group_id>/invites/<int:invite_id>/qr", groups.invite_qr, name="invite-qr"),
    path("groups/<int:group_id>/simplified", settlements.simplified, name="simplified"),
    path("groups", groups.groups, name="groups"),
    path("groups/<int:group_id>", groups.group_detail, name="group-detail"),
    path("groups/<int:group_id>/members", groups.members, name="members"),
    path("groups/<int:group_id>/members/<int:user_id>/role", groups.member_role, name="member-role"),
    path("groups/<int:group_id>/members/<int:user_id>/remove", groups.member_remove, name="member-remove"),
    path("groups/<int:group_id>/leave", groups.group_leave, name="group-leave"),
    path("groups/<int:group_id>/delete", groups.group_delete, name="group-delete"),
    path("groups/<int:group_id>/expenses", expenses.group_expenses, name="group-expenses"),
    path("groups/<int:group_id>/balances", balances, name="group-balances"),
    path("expenses", expenses.expenses, name="expenses"),
    path("expenses/<int:expense_id>", expenses.expense_detail, name="expense-detail"),
    path("expenses/<int:expense_id>/delete", expenses.expense_delete, name="expense-delete"),
    path("groups/<int:group_id>/categories", expenses.categories, name="categories"),
    path("groups/<int:group_id>/categories/<int:category_id>", expenses.categories, name="category-detail"),
    path("settlements", settlements.settlements, name="settlements"),
    path("groups/<int:group_id>/settlements", settlements.group_settlements, name="group-settlements"),
    path("settlements/<int:settlement_id>/confirm", settlements.settlement_action, {"action": "confirm"}, name="settlement-confirm"),
    path("settlements/<int:settlement_id>/reject", settlements.settlement_action, {"action": "reject"}, name="settlement-reject"),
    path("settlements/<int:settlement_id>/cancel", settlements.settlement_action, {"action": "cancel"}, name="settlement-cancel"),
    path("groups/<int:group_id>/activity", activity, name="activity"),
    path("balances", balances, name="balances"),
]
