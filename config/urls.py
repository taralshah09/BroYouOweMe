from django.urls import path

from apps.accounts import views as accounts
from apps.expenses import views as expenses
from apps.groups import views as groups
from apps.settlements import views as settlements
from apps.activity.views import activity
from apps.settlements.views import balances

urlpatterns = [
    path("", accounts.home, name="home"),
    path("health", accounts.health, name="health"),
    path("signup", accounts.signup, name="signup"),
    path("login", accounts.login, name="login"),
    path("logout", accounts.logout, name="logout"),
    path("users", accounts.users, name="users"),
    path("groups", groups.groups, name="groups"),
    path("groups/<int:group_id>", groups.group_detail, name="group-detail"),
    path("groups/<int:group_id>/members", groups.members, name="members"),
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
