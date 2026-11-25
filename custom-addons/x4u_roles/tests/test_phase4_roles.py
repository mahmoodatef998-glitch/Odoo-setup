from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestPhase4Roles(TransactionCase):
    """UAT Phase 4.4: what each of the four UAT roles can and cannot do, with its 4U role only
    (Purchasing Officer, Storekeeper, Operation Manager for production, Accountant)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def user(role):
            account = new_test_user(cls.env, login="x4u_p4_" + role, groups="base.group_user")
            account.write({"role_line_ids": [Command.create({"role_id": cls.env.ref("x4u_roles." + role).id})]})
            return account

        cls.buyer = user("role_purchasing_officer")
        cls.store = user("role_storekeeper")
        cls.production = user("role_production")
        cls.accountant = user("role_accountant")
        vendor = cls.env["res.partner"].create({"name": "X4U Test P4 Vendor"})
        product = cls.env["product.product"].create({"name": "X4U Test P4 Part"})
        cls.order = cls.env["purchase.order"].create(
            {"partner_id": vendor.id, "order_line": [Command.create({"product_id": product.id, "product_qty": 1, "price_unit": 10.0})]}
        )
        cls.order.button_confirm()

    def _sees(self, user, menu):
        return self.env.ref(menu).id in self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()

    def _can(self, user, model, operation):
        try:
            self.env[model].with_user(user).check_access(operation)
        except AccessError:
            return False
        return True

    def test_purchasing_officer(self):
        """RFQ / PO and its print; no accounting, no manufacturing changes."""
        self.assertTrue(self._can(self.buyer, "purchase.order", "create"))
        report = self.env.ref("purchase.action_report_purchase_order")
        html = self.env["ir.actions.report"].with_user(self.buyer)._render_qweb_html(report, self.order.ids)[0]
        self.assertIn(self.order.name.encode(), html)
        self.assertFalse(self._sees(self.buyer, "account.menu_finance"), "no Accounting app")
        self.assertFalse(self._can(self.buyer, "mrp.production", "write"))

    def test_storekeeper(self):
        """Receives (with the Delivery Note) and delivers; buys and invoices nothing."""
        self.assertTrue(self._can(self.store, "stock.picking", "write"))
        self.assertTrue(self._can(self.store, "ir.attachment", "create"))
        self.assertFalse(self._can(self.store, "purchase.order", "create"))
        self.assertFalse(self._can(self.store, "account.move", "create"))
        self.assertFalse(self._sees(self.store, "account.menu_finance"))

    def test_operation_manager(self):
        """Makes and finishes manufacturing orders, consuming the parts."""
        self.assertTrue(self._can(self.production, "mrp.production", "create"))
        self.assertTrue(self._can(self.production, "mrp.production", "write"))
        self.assertTrue(self._can(self.production, "stock.move", "write"))

    def test_accountant(self):
        """Matches bills to receipts, posts invoices, reads the General Ledger, P&L and Balance Sheet;
        does not buy or sell."""
        self.assertTrue(self._can(self.accountant, "account.move", "create"))
        self.assertTrue(self._can(self.accountant, "stock.picking", "read"))
        self.assertFalse(self._can(self.accountant, "purchase.order", "create"))
        self.assertFalse(self._can(self.accountant, "sale.order", "create"))
        self.assertTrue(self._sees(self.accountant, "account.menu_finance_reports"), "Accounting > Reporting")
        if "general.ledger.report.wizard" in self.env:
            self.assertTrue(self._can(self.accountant, "general.ledger.report.wizard", "create"))
