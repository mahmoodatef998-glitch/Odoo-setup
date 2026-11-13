from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import X4uJobOrderCommon


@tagged("post_install", "-at_install")
class TestReadyGenerator(X4uJobOrderCommon):
    """Spec v0.7 G1-G6: a generator bought complete, not assembled."""

    def _sell_ready(self, qty=1):
        self.template.categ_id = self.env.ref("x4u_setup_base.categ_generators")
        self.template.list_price = 10000.0
        pricelist = self.env["product.pricelist"].create(
            {"name": "X4U Test Ready", "currency_id": self.env.company.currency_id.id}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "warehouse_id": self.warehouse.id,
                "pricelist_id": pricelist.id,
                "order_line": [
                    Command.create({"product_id": self.variant.id, "product_uom_qty": qty, "x4u_supply": "ready"})
                ],
            }
        )
        order.action_confirm()
        return order

    def _buy(self, order, price=7000.0):
        """Purchasing orders it from the request, the GM approves the PO (spec J15)."""
        lines = order.x4u_ready_order_ids.request_id.line_ids
        wizard = (
            self.env["purchase.request.line.make.purchase.order"]
            .with_context(active_model="purchase.request.line", active_ids=lines.ids)
            .create({"supplier_id": self.vendor_engine.id})
        )
        wizard.make_purchase_order()
        po = self.env["purchase.order"].search([("order_line.purchase_request_lines", "in", lines.ids)])
        po.order_line.price_unit = price
        po.with_user(self.buyer).button_confirm()
        if po.state == "to approve":
            po.with_user(self.manager).button_approve()
        self.assertEqual(po.state, "purchase")
        return po

    # G1-G2: Buy Ready opens one request for the complete generator, no Job Order with parts
    def test_buy_ready_opens_one_request(self):
        order = self._sell_ready()
        self.assertFalse(order.mrp_production_ids, "nothing to assemble")
        ready = order.x4u_ready_order_ids
        self.assertEqual(len(ready), 1)
        self.assertTrue(ready.name.startswith("RG"))
        self.assertEqual(ready.state, "waiting")
        self.assertEqual(ready.customer_id, self.customer)
        request = ready.request_id
        self.assertEqual(request.state, "approved")
        self.assertEqual(request.line_ids.product_id, self.variant, "the complete generator, not its parts")
        self.assertIn("Requested", ready.purchase_status)
        self.assertEqual(order.order_line.analytic_distribution, {str(ready.analytic_account_id.id): 100.0})

    # G3-G6: received with its 4U serial as a finished good, delivered, and its margin
    def test_ready_generator_full_cycle(self):
        order = self._sell_ready()
        ready = order.x4u_ready_order_ids
        po = self._buy(order)
        self.assertIn(po.name, ready.purchase_status)
        receipt = po.picking_ids
        self._validate(receipt)
        self.assertEqual(ready.state, "in_stock")
        self.assertEqual(ready.lot_id.name, ready.name, "the serial is the Ready Job Order number")
        quant = self.env["stock.quant"].search(
            [("lot_id", "=", ready.lot_id.id), ("location_id", "=", self.warehouse.lot_stock_id.id)]
        )
        self.assertEqual(quant.quantity, 1.0, "in WH/Stock as a finished generator")
        self.assertEqual(ready.generator_id.sale_order_id, order)
        self.assertEqual(ready.generator_id.customer_id, self.customer)
        categ = self.template.categ_id.with_company(self.env.company)
        if self.env.company.anglo_saxon_accounting and categ.property_valuation == "real_time":
            entry = receipt.move_ids.stock_valuation_layer_ids.account_move_id
            inventory = entry.line_ids.filtered(lambda line: line.account_id == categ.property_stock_valuation_account_id)
            self.assertEqual(inventory.debit, 7000.0, "Dr Finished Generators at what it cost")

        self._deliver(order)
        self.assertEqual(ready.state, "delivered")
        invoice = order._create_invoices()
        invoice.action_post()
        if self.env.company.anglo_saxon_accounting and categ.property_valuation == "real_time":
            self.assertAlmostEqual(ready.margin, 3000.0)
        else:
            self.assertAlmostEqual(ready.margin, 10000.0)

    def test_two_ready_generators(self):
        order = self._sell_ready(qty=2)
        ready = order.x4u_ready_order_ids
        self.assertEqual(len(ready), 2)
        self._buy(order)
        self._validate(order.x4u_ready_order_ids.purchase_order_id.picking_ids)
        self.assertEqual(set(ready.mapped("state")), {"in_stock"})
        self.assertEqual(sorted(ready.lot_id.mapped("name")), sorted(ready.mapped("name")))

    def test_buy_ready_is_for_generators(self):
        part = self.engine
        with self.assertRaises(UserError):
            self.env["sale.order"].create(
                {
                    "partner_id": self.customer.id,
                    "order_line": [Command.create({"product_id": part.id, "x4u_supply": "ready"})],
                }
            )

    def test_assemble_unchanged(self):
        _order, production = self._sell()
        self.assertEqual(len(production), 1)
        self.assertFalse(_order.x4u_ready_order_ids)
