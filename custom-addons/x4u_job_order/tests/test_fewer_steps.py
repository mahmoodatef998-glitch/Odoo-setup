from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import X4uJobOrderCommon


@tagged("post_install", "-at_install")
class TestFewerSteps(X4uJobOrderCommon):
    """The user, 2026-11-26: fewer steps - the RFQs of a Job Order in one click, Deliver Materials
    filled with serials, Finish of one generator straight to its screen."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Like the Purchasing roles of x4u_roles: they manage the material requests.
        cls.buyer = new_test_user(
            cls.env,
            login="x4u_fewer_buyer",
            groups="base.group_user,purchase.group_purchase_user,purchase_request.group_purchase_request_manager",
        )

    def _components(self, production):
        moves = production.move_raw_ids
        return {role: moves.filtered(lambda m, r=role: m.x4u_role == r).product_id for role in ("engine", "alternator", "body")}

    # The user, 2026-11-26: a model Built from CKD - its CKD card is made, its Job Orders take it
    def test_model_built_from_ckd(self):
        template = self.variant.product_tmpl_id
        template.x4u_built_from_ckd = True
        ckd = self.variant.x4u_ckd_product_id
        self.assertTrue(ckd, "the CKD card of the variant")
        self.assertEqual(ckd.categ_id, self.env.ref("x4u_setup_base.categ_ckd"))
        self.assertEqual(ckd.tracking, "serial", "one serial, the engine's")
        self.assertIn(self.engine.name, ckd.name)
        self.assertIn(ckd, template.x4u_ckd_product_ids)
        template.write({"x4u_built_from_ckd": False})
        template.write({"x4u_built_from_ckd": True})
        self.assertEqual(self.variant.x4u_ckd_product_id, ckd, "the same card, not a second one")
        _order, production = self._sell()
        self.assertTrue(production.x4u_uses_ckd)
        roles = set(production.move_raw_ids.filtered(lambda m: m.state != "cancel").mapped("x4u_role"))
        self.assertIn("ckd", roles)
        self.assertFalse(roles & {"engine", "alternator"}, "the CKD instead of the engine and the alternator")
        requested = production._x4u_purchase_requests().line_ids.filtered(lambda line: not line.cancelled).product_id
        self.assertIn(ckd, requested, "the material request asks for the CKD")
        self.assertNotIn(self.engine, requested)

    # The user, 2026-11-26: on the PO - the engine, CKD ticked, its alternator: the line becomes the
    # full CKD at the same price, received with the engine's serial
    def test_ckd_on_the_purchase_order(self):
        order = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor_engine.id,
                "order_line": [Command.create({"product_id": self.engine.id, "product_qty": 1, "price_unit": 31000.0})],
            }
        )
        line = order.order_line
        self.assertTrue(line.x4u_is_engine)
        line.write({"x4u_ckd": True, "x4u_ckd_alternator_id": self.alt_stamford.id})
        ckd = line.product_id
        self.assertEqual(ckd.categ_id, self.env.ref("x4u_setup_base.categ_ckd"))
        self.assertIn(self.engine.name, ckd.name)
        self.assertIn(self.alt_stamford.name, ckd.name)
        self.assertEqual(line.price_unit, 31000.0, "the price stays")
        again = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor_engine.id,
                "order_line": [Command.create({
                    "product_id": self.engine.id, "product_qty": 1, "price_unit": 30000.0,
                    "x4u_ckd": True, "x4u_ckd_alternator_id": self.alt_stamford.id,
                })],
            }
        )
        self.assertEqual(again.order_line.product_id, ckd, "the same CKD card")
        again.order_line.write({"x4u_ckd_alternator_id": self.alt_aqt.id})
        self.assertIn(self.alt_aqt.name, again.order_line.product_id.name, "another alternator: that pair's CKD")
        self.assertEqual(again.order_line.price_unit, 30000.0)
        again.order_line.write({"x4u_ckd": False})
        self.assertEqual(again.order_line.product_id, self.engine, "unticked: the engine again")
        order.button_confirm()
        receipt = order.picking_ids
        receipt.move_ids.x4u_serials = "X4U-CKD-E1"
        receipt.button_validate()
        self.assertEqual(receipt.state, "done")
        self.assertEqual(self._lots(ckd).mapped("name"), ["X4U-CKD-E1"], "one serial, the engine's")
        with self.assertRaisesRegex(UserError, "confirmed"):
            order.order_line.write({"x4u_ckd_alternator_id": self.alt_aqt.id})

    # The user, 2026-11-26: a product found by its serial; its tab says how many serials are in stock
    def test_serials_on_the_product(self):
        self._stock(self.engine, 2)
        self._stock(self.alt_stamford, 1)
        engine = self.engine.product_tmpl_id
        lots = self._lots(self.engine)
        self.assertTrue(engine.x4u_has_serials)
        self.assertEqual(engine.x4u_serial_count, 2)
        self.assertEqual(engine.x4u_serial_lot_ids, lots)
        Template = self.env["product.template"]
        self.assertEqual(Template.search([("x4u_serial_search", "ilike", lots[:1].name)]), engine)
        alternator = self.alt_stamford.product_tmpl_id
        serial = self.env["x4u.alternator.serial"].search([("product_id", "=", self.alt_stamford.id)])
        self.assertTrue(alternator.x4u_has_serials)
        self.assertEqual(alternator.x4u_serial_count, 1)
        self.assertEqual(alternator.x4u_serial_alternator_ids, serial)
        self.assertEqual(Template.search([("x4u_serial_search", "ilike", serial.name)]), alternator)
        self.assertFalse(Template.search([("x4u_serial_search", "ilike", "NO-SUCH-SERIAL-77")]))

    def test_buy_missing_parts(self):
        _order, production = self._sell()
        job = production.x4u_job_id
        lines = production._x4u_purchase_requests().line_ids
        self.assertTrue(lines, "nothing in stock: the parts are requested")
        for product in lines.product_id:
            vendor = self.vendor_engine if product == self.engine else self.vendor_aqt
            self.env["product.supplierinfo"].create({"partner_id": vendor.id, "product_tmpl_id": product.product_tmpl_id.id, "price": 100.0})
        action = job.with_user(self.buyer).action_buy_missing_parts()
        orders = self.env["purchase.order"].browse(action["domain"][0][2])
        self.assertEqual(set(orders.partner_id.ids), {self.vendor_engine.id, self.vendor_aqt.id}, "one RFQ per vendor")
        self.assertEqual(orders.order_line.product_id, lines.product_id)
        lines.invalidate_recordset()
        self.assertTrue(all(line.purchase_lines for line in lines))
        with self.assertRaisesRegex(UserError, "no part left to buy"):
            job.with_user(self.buyer).action_buy_missing_parts()

    def test_buy_missing_parts_needs_a_vendor(self):
        _order, production = self._sell()
        with self.assertRaisesRegex(UserError, "No vendor"):
            production.x4u_job_id.with_user(self.buyer).action_buy_missing_parts()

    def test_deliver_materials_suggests_the_oldest_serials(self):
        _order, probe = self._sell()
        parts = self._components(probe)
        for product in parts.values():
            self._stock(product, 2)
        _order, production = self._sell()
        action = production.x4u_job_id.action_deliver_materials()
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        line = wizard.line_ids.filtered(lambda l: l.production_id == production)
        engines = self._lots(parts["engine"]).sorted("id")
        self.assertEqual(line.engine_lot_id, engines[:1], "the oldest engine serial")
        self.assertEqual(line.body_lot_id, self._lots(parts["body"]).sorted("id")[:1])
        self.assertTrue(line.alternator_serial_id, "an alternator serial from the receipt")
        wizard.action_confirm()
        self.assertEqual(production.x4u_job_state, "material_delivered")
        # One generator: Finish opens its own screen with the serials fitted.
        res = production.x4u_job_id.with_user(self.operation).action_finish()
        self.assertEqual(res["res_model"], "x4u.job.order.finish")
