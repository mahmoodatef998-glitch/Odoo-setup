from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import X4uJobOrderCommon


@tagged("post_install", "-at_install")
class TestOrderDelivery(X4uJobOrderCommon):
    """Spec v0.13: part of an order delivered within what was paid (L1, L2); the tax invoice has
    every generator and takes the rest out of stock (L3, L4)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tax = cls.env["account.tax"].create({"name": "X4U Test Delivery VAT 5%", "amount": 5.0, "type_tax_use": "sale"})
        # The company currency: AED is only active where the UAE chart is.
        cls.pricelist = cls.env["product.pricelist"].create(
            {"name": "X4U Test Delivery", "currency_id": cls.env.company.currency_id.id}
        )

    def _sell(self, term="x4u_setup_base.payment_term_50_50", finish=2):
        """Two generators at 10,000 + 5% = 10,500 each (21,000), `finish` of them made and in stock."""
        for part in (self.engine, self.alt_stamford, self.body_canopy):
            self._stock(part, 2)
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "warehouse_id": self.warehouse.id,
                "pricelist_id": self.pricelist.id,
                "payment_term_id": self.env.ref(term).id,
                "order_line": [
                    Command.create(
                        {"product_id": self.variant.id, "product_uom_qty": 2, "price_unit": 10000.0, "tax_id": [Command.set(self.tax.ids)]}
                    )
                ],
            }
        )
        order.action_confirm()
        self.assertEqual(order.amount_total, 21000.0)
        job = order.x4u_job_ids
        for production in job.production_ids.sorted("name")[:finish]:
            self._deliver_materials(production)
            self._finish(production)
        return order, job

    def _pay(self, order, amount):
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.customer.id,
                "amount": amount,
                "x4u_sale_order_id": order.id,
            }
        )
        payment.action_post()
        self.env.invalidate_all()
        return payment

    def _ship(self, job, count):
        """Deliver Generators as the Storekeeper: the first `count` generators in stock."""
        action = job.with_user(self.storekeeper).action_ship()
        wizard = self.env[action["res_model"]].with_user(self.storekeeper).browse(action["res_id"])
        wizard.line_ids.sorted("lot_id")[:count].write({"selected": True})
        return wizard

    # T46 + T47 (L1, L2): 50 / 50, half paid: one generator leaves, not two, however it is delivered
    def test_deliver_within_paid(self):
        order, job = self._sell()
        self._pay(order, 10500.0)
        self.assertTrue(job.can_ship)
        wizard = self._ship(job, 2)
        self.assertEqual(len(wizard.line_ids), 2, "a line per generator in stock")
        self.assertEqual((wizard.amount_paid, wizard.amount_selected), (10500.0, 21000.0))
        with self.assertRaisesRegex(UserError, "paid before delivery"):
            wizard.action_confirm()
        wizard.line_ids.write({"selected": False})
        wizard.line_ids.sorted("lot_id")[:1].selected = True
        shipped = wizard.line_ids.filtered("selected").lot_id
        wizard.action_confirm()
        delivered = order.picking_ids.filtered(lambda p: p.picking_type_code == "outgoing" and p.state == "done")
        self.assertEqual(delivered.move_line_ids.lot_id, shipped, "the Delivery Note has that generator, by its serial")
        self.assertEqual(order.order_line.qty_delivered, 1.0)
        self.assertEqual((job.delivered_count, job.progress), (1, "Finished 2 / 2 · Delivered 1 / 2"))
        # The other one, from Inventory: refused too.
        backorder = order.picking_ids.filtered(lambda p: p.picking_type_code == "outgoing" and p.state not in ("done", "cancel"))
        self.assertEqual(len(backorder), 1, "the other generator waits on the next delivery")
        with self.assertRaisesRegex(UserError, "paid before delivery"):
            self._validate(backorder)
        self._pay(order, 10500.0)
        self._validate(backorder)
        self.assertEqual(job.state, "delivered")

    # T48 (L3, L4): the tax invoice waits for every generator; confirming it takes the rest out of stock
    def test_tax_invoice_takes_the_rest(self):
        order, job = self._sell(finish=1)
        self._pay(order, 10500.0)
        with self.assertRaisesRegex(UserError, "not ready yet"):
            order.action_x4u_create_tax_invoice()
        self._ship(job, 1).action_confirm()
        last = job.production_ids.filtered(lambda p: p.state != "done")
        self._deliver_materials(last)
        self._finish(last)
        action = order.action_x4u_create_tax_invoice()
        invoice = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(invoice.amount_total, 21000.0, "every generator on the tax invoice")
        self.assertEqual(order.order_line.qty_delivered, 1.0, "nothing more leaves before the Confirm")
        invoice.action_post()
        self.env.invalidate_all()
        self.assertEqual(order.order_line.qty_delivered, 2.0, "the last generator left with the tax invoice")
        self.assertEqual(last.x4u_job_state, "delivered")
        self.assertEqual(job.state, "delivered")
        self.assertEqual(invoice.amount_residual, 10500.0, "the payment applied")
        self.assertFalse(order._x4u_generator_lots_in_stock())

    # T49 (L1): credit terms: delivered before any payment
    def test_credit_terms_deliver_unpaid(self):
        order, job = self._sell(term="x4u_setup_base.payment_term_60_days")
        self.assertFalse(order._x4u_delivery_within_paid())
        wizard = self._ship(job, 2)
        self.assertFalse(wizard.limited)
        wizard.action_confirm()
        self.assertEqual(order.order_line.qty_delivered, 2.0)
        self.assertEqual(job.state, "delivered")
