from odoo import Command
from odoo.tests import TransactionCase, new_test_user, tagged

MANAGERS = {
    "sales_team.group_sale_manager",
    "purchase.group_purchase_manager",
    "purchase_request.group_purchase_request_manager",
    "stock.group_stock_manager",
    "mrp.group_mrp_manager",
    "quality_control_oca.group_quality_control_manager",
    "account.group_account_manager",
}
# Role -> (groups it must give, groups it must not give)
ROLES = {
    "role_salesperson": (
        {"sales_team.group_sale_salesman"},
        {"sales_team.group_sale_manager", "purchase.group_purchase_user", "stock.group_stock_user", "base.group_system"},
    ),
    "role_sales_manager": ({"sales_team.group_sale_manager"}, {"purchase.group_purchase_user"}),
    "role_purchasing_officer": (
        {"purchase.group_purchase_user", "purchase_request.group_purchase_request_manager"},
        {"purchase.group_purchase_manager", "sales_team.group_sale_salesman"},
    ),
    "role_general_manager": (MANAGERS, {"base.group_system"}),
    "role_storekeeper": ({"stock.group_stock_user"}, {"stock.group_stock_manager", "sales_team.group_sale_salesman"}),
    "role_production": ({"mrp.group_mrp_user"}, {"mrp.group_mrp_manager", "purchase.group_purchase_user"}),
    "role_quality_inspector": (
        {"quality_control_oca.group_quality_control_user"},
        {"quality_control_oca.group_quality_control_manager", "sales_team.group_sale_salesman"},
    ),
    "role_accountant": ({"account.group_account_manager"}, {"purchase.group_purchase_user", "sales_team.group_sale_salesman"}),
    "role_administrator": (MANAGERS | {"base.group_system"}, set()),
}


@tagged("post_install", "-at_install")
class TestRoles(TransactionCase):
    def _user(self, *roles):
        user = new_test_user(self.env, login="x4u_role_%s" % "_".join(roles), groups="base.group_user")
        user.write({"role_line_ids": [Command.create({"role_id": self.env.ref("x4u_roles." + r).id}) for r in roles]})
        return user

    def test_each_role_gives_exactly_its_rights(self):
        for role, (given, not_given) in ROLES.items():
            user = self._user(role)
            for group in given:
                self.assertTrue(user.has_group(group), "%s should give %s" % (role, group))
            for group in not_given:
                self.assertFalse(user.has_group(group), "%s should not give %s" % (role, group))

    def test_only_the_general_manager_approves_purchases(self):
        self.assertFalse(self._user("role_purchasing_officer").has_group("purchase.group_purchase_manager"))
        self.assertTrue(self._user("role_general_manager").has_group("purchase.group_purchase_manager"))

    def test_changing_the_role_removes_the_old_rights(self):
        user = self._user("role_storekeeper")
        self.assertTrue(user.has_group("stock.group_stock_user"))
        user.write(
            {
                "role_line_ids": [Command.clear()]
                + [Command.create({"role_id": self.env.ref("x4u_roles.role_salesperson").id})]
            }
        )
        self.assertFalse(user.has_group("stock.group_stock_user"))
        self.assertTrue(user.has_group("sales_team.group_sale_salesman"))
