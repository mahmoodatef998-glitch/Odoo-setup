from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

MANAGERS = {
    "sales_team.group_sale_manager",
    "purchase.group_purchase_manager",
    "purchase_request.group_purchase_request_manager",
    "stock.group_stock_manager",
    "mrp.group_mrp_manager",
    "quality_control_oca.group_quality_control_manager",
    "account.group_account_manager",
    "account.group_account_user",
    "hr.group_hr_manager",
    "hr_holidays.group_hr_holidays_manager",
    "payroll.group_payroll_manager",
}
# Role -> (groups it must give, groups it must not give)
ROLES = {
    "role_salesperson": (
        {"sales_team.group_sale_salesman"},
        {
            "sales_team.group_sale_manager",
            "purchase.group_purchase_user",
            "stock.group_stock_user",
            "base.group_system",
            "account.group_account_user",
            "hr.group_hr_user",
            "payroll.group_payroll_user",
        },
    ),
    "role_sales_manager": ({"sales_team.group_sale_manager"}, {"purchase.group_purchase_user"}),
    "role_purchasing_officer": (
        {
            "purchase.group_purchase_user",
            "purchase_request.group_purchase_request_manager",
            "base.group_partner_manager",
            "x4u_job_order.group_x4u_job_order_viewer",
            # Receives purchases and writes their serials (x4u_job_order spec v0.8 N2).
            "stock.group_stock_user",
            "x4u_roles.group_x4u_receipts_only",
        },
        {
            "purchase.group_purchase_manager",
            "sales_team.group_sale_salesman",
            "mrp.group_mrp_user",
            "stock.group_stock_manager",
        },
    ),
    "role_general_manager": (MANAGERS, {"base.group_system"}),
    "role_storekeeper": (
        {"stock.group_stock_user", "x4u_job_order.group_x4u_job_order_viewer"},
        {"stock.group_stock_manager", "sales_team.group_sale_salesman", "mrp.group_mrp_user"},
    ),
    # Operation Manager (spec v0.4): finishes the Job Orders.
    "role_production": ({"mrp.group_mrp_user"}, {"mrp.group_mrp_manager", "purchase.group_purchase_user"}),
    "role_quality_inspector": (
        {"quality_control_oca.group_quality_control_user", "x4u_job_order.group_x4u_job_order_viewer"},
        {"quality_control_oca.group_quality_control_manager", "sales_team.group_sale_salesman", "mrp.group_mrp_user"},
    ),
    "role_accountant": (
        {
            "account.group_account_manager",
            "account.group_account_user",
            "payroll.group_payroll_manager",
            "hr.group_hr_user",
            "base.group_partner_manager",
        },
        {"purchase.group_purchase_user", "sales_team.group_sale_salesman", "hr.group_hr_manager"},
    ),
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

    # x4u_job_order spec v0.8 N2 (T21): Purchasing receives an engine with its serial, and changes
    # no other transfer and no stock count
    def test_purchasing_receives_only(self):
        buyer = self._user("role_purchasing_officer")
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        engine = self.env["product.product"].create(
            {
                "name": "X4U Test Role Engine",
                "is_storable": True,
                "categ_id": self.env.ref("x4u_setup_base.categ_engines").id,
            }
        )
        self.assertEqual(engine.tracking, "serial")
        suppliers = self.env.ref("stock.stock_location_suppliers")
        customers = self.env.ref("stock.stock_location_customers")

        def transfer(picking_type, source, destination):
            picking = self.env["stock.picking"].create(
                {
                    "picking_type_id": picking_type.id,
                    "location_id": source.id,
                    "location_dest_id": destination.id,
                    "move_ids": [
                        Command.create(
                            {
                                "name": engine.name,
                                "product_id": engine.id,
                                "product_uom_qty": 1,
                                "product_uom": engine.uom_id.id,
                                "location_id": source.id,
                                "location_dest_id": destination.id,
                            }
                        )
                    ],
                }
            )
            picking.action_confirm()
            return picking

        receipt = transfer(warehouse.in_type_id, suppliers, warehouse.lot_stock_id).with_user(buyer)
        receipt.move_ids.quantity = 1
        receipt.move_ids.move_line_ids.lot_name = "X4U-ROLE-E-1"
        receipt.move_ids.picked = True
        receipt.button_validate()
        self.assertEqual(receipt.state, "done")

        delivery = transfer(warehouse.out_type_id, warehouse.lot_stock_id, customers)
        delivery.action_assign()
        with self.assertRaises(AccessError):
            delivery.with_user(buyer).move_ids.picked = True
            delivery.with_user(buyer).button_validate()
        quant = self.env["stock.quant"].search([("product_id", "=", engine.id), ("location_id", "=", warehouse.lot_stock_id.id)])
        with self.assertRaises(AccessError):
            quant.with_user(buyer).with_context(inventory_mode=True).action_apply_inventory()
