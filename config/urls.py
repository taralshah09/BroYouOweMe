from django.urls import path

from apps.accounts import views as accounts
from apps.expenses import views as expenses
from apps.groups import views as groups
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
    path("balances", balances, name="balances"),
]
