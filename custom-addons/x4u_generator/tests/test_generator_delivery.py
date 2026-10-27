from odoo import fields
from odoo.tests import tagged

from .common import X4uGeneratorCommon


@tagged("post_install", "-at_install")
class TestGeneratorDelivery(X4uGeneratorCommon):
    # T6 - delivery to the customer fills the card
    def test_delivery_fills_card(self):
        lot = self._create_lot("X4U-T6-0001")
        self._create_inspection(lot, "success")
        order, picking = self._sell(lot)
        self._validate(picking, self.stock_user)
        card = lot.x4u_generator_id
        self.assertEqual(card.state, "delivered")
        self.assertEqual(card.customer_id, self.customer)
        self.assertEqual(card.site_address_id, self.customer)
        self.assertEqual(card.sale_order_id, order)
        self.assertEqual(card.delivery_picking_id, picking)
        self.assertEqual(
            card.delivery_date, fields.Date.context_today(card, picking.date_done)
        )
        self.assertEqual(card.warranty_state, "active")
        self.assertEqual(order.x4u_generator_count, 1)
        self.assertEqual(self.customer.x4u_generator_count, 1)

    # T7 - return from the customer puts the card back in stock
    def test_return_puts_card_back_in_stock(self):
        lot = self._create_lot("X4U-T7-0001")
        self._create_inspection(lot, "success")
        _order, picking = self._sell(lot)
        self._validate(picking, self.stock_user)
        card = lot.x4u_generator_id
        card.commissioning_date = card.delivery_date
        self.assertEqual(card.state, "commissioned")
        self._return(picking, self.stock_user)
        self.assertEqual(card.state, "in_stock")
        self.assertFalse(card.customer_id)
        self.assertFalse(card.sale_order_id)
        self.assertFalse(card.delivery_date)
        self.assertFalse(card.commissioning_date)
        self.assertEqual(card.warranty_state, "not_started")

    # T10 - no quality gate before delivery (Q3 cancelled 2026-10-27, x4u_job_order v0.4 V7)
    def test_delivery_not_blocked_by_qc(self):
        lot = self._create_lot("X4U-T10-0001")
        _order, picking = self._sell(lot)
        self._validate(picking, self.stock_user)
        self.assertEqual(lot.x4u_generator_id.state, "delivered")

    def test_regular_product_delivery_not_blocked(self):
        lot = self._create_lot("X4U-T10-PART", self.part_product)
        _order, picking = self._sell(lot)
        self._validate(picking, self.stock_user)
        self.assertFalse(lot.x4u_generator_ids)
