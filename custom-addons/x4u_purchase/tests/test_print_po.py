from lxml import etree

from odoo import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestPrintPO(TransactionCase):
    """UAT Phase 3.1 (spec §9 D1): a confirmed PO is printed from its header, by Purchasing too."""

    def test_print_po_after_confirm(self):
        buyer = new_test_user(self.env, login="x4u_print_buyer", groups="base.group_user,purchase.group_purchase_user")
        vendor = self.env["res.partner"].create({"name": "X4U Test Print Vendor"})
        product = self.env["product.product"].create({"name": "X4U Test Print Part"})
        order = self.env["purchase.order"].create(
            {
                "partner_id": vendor.id,
                "order_line": [Command.create({"product_id": product.id, "product_qty": 2, "price_unit": 50.0})],
            }
        )
        order.button_confirm()
        if order.state == "to approve":
            order.button_approve()
        self.assertEqual(order.state, "purchase")

        report = self.env.ref("purchase.action_report_purchase_order")
        arch = etree.fromstring(self.env["purchase.order"].get_view(view_type="form")["arch"])
        [button] = arch.xpath("//header/button[@string='Print PO']")
        self.assertEqual(button.get("name"), str(report.id))
        self.assertIn("'purchase'", button.get("invisible"))

        html, _type = self.env["ir.actions.report"].with_user(buyer)._render_qweb_html(report, order.ids)
        self.assertIn(order.name.encode(), html)
