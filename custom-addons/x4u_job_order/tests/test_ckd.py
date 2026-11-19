from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .common import X4uJobOrderCommon


@tagged("post_install", "-at_install")
class TestCkd(X4uJobOrderCommon):
    """Spec v0.9: CKD instead of the engine and the alternator (C1-C6), serials changed by the
    Administrator, the GM and the Operation Manager only (E1-E3), the PI on the Job Order (P1)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.ckd = cls.env["product.product"].create(
            {
                "name": "X4U Test CKD E-500",
                "is_storable": True,
                "categ_id": ref("x4u_setup_base.categ_ckd").id,
                "purchase_request": True,
                "route_ids": [
                    Command.set([ref("purchase_stock.route_warehouse0_buy").id, ref("stock.route_warehouse0_mto").id])
                ],
            }
        )
        cls.operation.groups_id = [Command.link(ref("x4u_job_order.group_x4u_edit_serials").id)]

    def _parts(self, production):
        return set(production.move_raw_ids.filtered(lambda m: m.state != "cancel").mapped("x4u_role"))

    def _request_lines(self, production, product):
        """The material request lines of the Job Order's parts as they are now."""
        lines = production._x4u_component_moves()._x4u_request_lines()
        return lines.filtered(lambda line: line.product_id == product)

    def _said(self, production, text):
        return any(text in (message.body or "") for message in production.message_ids)

    def _use_ckd(self, production, user=None):
        action = production.with_user(user or self.operation).action_x4u_use_ckd()
        with Form(self.env[action["res_model"]].with_user(user or self.operation).with_context(**action["context"])) as form:
            form.product_id = self.ckd
            self.assertIn(self.ckd, form.allowed_product_ids)
        form.record.action_confirm()

    # T29 (C1-C2): a CKD is tracked and valued by its serial, and comes in with one
    def test_ckd_goes_by_serial(self):
        self.assertEqual(self.ckd.tracking, "serial")
        self.assertTrue(self.ckd.lot_valuated)
        receipt = self._receipt(self.ckd, 1)
        receipt.move_ids.quantity = 1
        receipt.move_ids.picked = True
        with self.assertRaises(UserError):
            receipt.button_validate()
        receipt.move_ids.move_line_ids.lot_name = "X4U-CKD-5001"
        receipt.button_validate()
        self.assertEqual(self._lots(self.ckd).mapped("name"), ["X4U-CKD-5001"])

    # T30 (C3-C4): Use CKD replaces the engine and the alternator, in the material request too;
    # Use Engine + Alternator puts them back; only before Deliver Materials
    def test_use_ckd_and_back(self):
        _order, production = self._sell()
        self.assertEqual(self._parts(production), {"engine", "alternator", "body"})
        self.assertTrue(production.x4u_can_switch_parts)
        self.assertFalse(production.x4u_uses_ckd)
        with self.assertRaises(UserError, msg="the Storekeeper delivers, he does not choose the parts"):
            production.with_user(self.storekeeper).action_x4u_use_ckd()
        engine_line = self._request_lines(production, self.engine)
        alternator_line = self._request_lines(production, self.alt_stamford)
        self.assertTrue(engine_line and alternator_line)
        self._use_ckd(production)
        self.assertEqual(self._parts(production), {"ckd", "body"})
        self.assertTrue(production.x4u_uses_ckd)
        self.assertTrue(engine_line.cancelled, "the engine leaves the material request")
        self.assertTrue(alternator_line.cancelled)
        ckd_line = self._request_lines(production, self.ckd)
        self.assertEqual(len(ckd_line), 1)
        self.assertFalse(ckd_line.cancelled)
        self.assertEqual(ckd_line.request_id.state, "approved")
        self.assertTrue(self._said(production, "X4U Test CKD E-500 instead of"))
        self.assertEqual(production.x4u_job_state, "waiting_parts")
        # And back to the bill of materials.
        production.with_user(self.operation).action_x4u_use_parts()
        self.assertEqual(self._parts(production), {"engine", "alternator", "body"})
        self.assertTrue(ckd_line.cancelled)
        self.assertTrue(self._request_lines(production, self.engine).filtered(lambda line: not line.cancelled))
        # Once the parts are delivered, they stay.
        for part in (self.engine, self.alt_stamford, self.body_canopy):
            self._stock(part, 1)
        self._deliver_materials(production)
        self.assertEqual(production.x4u_job_state, "material_delivered")
        self.assertFalse(production.x4u_can_switch_parts)
        with self.assertRaises(UserError):
            production.with_user(self.operation).action_x4u_use_ckd()

    # C4: an engine already on an RFQ stays bought; it comes in free in stock for another Job Order
    def test_ordered_parts_stay_bought(self):
        _order, production = self._sell()
        orders = self._order_parts(production)
        engine_line = self._request_lines(production, self.engine)
        self._use_ckd(production)
        self.assertFalse(engine_line.cancelled, "Purchasing already ordered it")
        self.assertTrue(self._said(production, "Already ordered"))
        engine_po = orders.filtered(lambda po: po.partner_id == self.vendor_engine)
        engine_po.with_user(self.manager).button_confirm()
        self._validate(engine_po.picking_ids)
        stock = self.warehouse.lot_stock_id
        self.assertEqual(self.engine.with_context(location=stock.id).free_qty, 1, "free in stock")
        self.assertEqual(production.x4u_job_state, "waiting_parts", "it waits for its CKD")

    # T31 (C5-C6): Deliver Materials needs the CKD serial; the card takes it as the engine serial, and
    # the generator is worth that very CKD + the body + 20%
    def test_deliver_ckd_by_serial(self):
        self.template.categ_id = self.env.ref("x4u_setup_base.categ_generators")
        self._stock(self.ckd, 1, price=1700.0)
        self._stock(self.ckd, 1, price=1500.0)
        self._stock(self.body_canopy, 1, price=300.0)
        _order, production = self._sell()
        self._use_ckd(production)
        self.assertEqual(production.x4u_job_state, "parts_ready")
        action = production.with_user(self.storekeeper).action_x4u_deliver_materials()
        wizard = self.env[action["res_model"]].with_user(self.storekeeper).browse(action["res_id"])
        ckd_line = wizard.line_ids.filtered(lambda line: line.x4u_role == "ckd")
        self.assertEqual(len(ckd_line), 1)
        self.assertEqual(len(ckd_line.available_lot_ids), 2)
        # Without its serial the CKD stays in stock, and the Job Order waits for it; the body goes.
        body_line = wizard.line_ids.filtered(lambda line: line.x4u_role == "body")
        body_line.lot_id = body_line.available_lot_ids[:1]
        wizard.action_confirm()
        self.assertEqual(production.x4u_job_state, "parts_ready")
        dear = self._lots(self.ckd).filtered(lambda lot: lot.avg_cost == 1700.0)
        self._deliver_materials(production, lots={self.ckd: dear})
        self.assertEqual(production.x4u_job_state, "material_delivered")
        card = production.x4u_generator_id
        self.assertEqual((card.x4u_engine_lot_id, card.engine_serial), (dear, dear.name))
        self.assertFalse(card.alternator_serial)
        self.assertEqual(self.env["mrp.production"].search([("x4u_serial_search", "=", dear.name)]), production, "S1")
        self._finish(production)
        self.assertEqual(production.state, "done", "no BoM consumption warning: the CKD is on purpose")
        finished = production.move_finished_ids.filtered(lambda m: m.product_id == production.product_id)
        self.assertAlmostEqual(sum(finished.stock_valuation_layer_ids.mapped("value")), (1700.0 + 300.0) * 1.2)

    # T32 (E1-E3): the Storekeeper does not change a serial after the receipt; the Operation Manager
    # does, and the generator card follows
    def test_change_a_serial(self):
        receipt = self._receipt(self.alt_stamford, 1)
        receipt.move_ids.quantity = 1
        receipt.move_ids.x4u_alternator_serials = "A-90"
        receipt.move_ids.picked = True
        receipt.button_validate()
        for part in (self.engine, self.body_canopy):
            self._stock(part, 1)
        _order, production = self._sell()
        alternator = self.env["x4u.alternator.serial"].search([("name", "=", "A-90")])
        action = production.with_user(self.storekeeper).action_x4u_deliver_materials()
        wizard = self.env[action["res_model"]].with_user(self.storekeeper).browse(action["res_id"])
        wizard.line_ids.filtered(lambda line: line.x4u_role == "alternator").alternator_serial_id = alternator
        for line in wizard.line_ids.filtered(lambda line: line.x4u_role in ("engine", "body")):
            line.lot_id = line.available_lot_ids[:1]
        wizard.action_confirm()
        card = production.x4u_generator_id
        engine = card.x4u_engine_lot_id
        self.assertTrue(engine)
        for record, name in ((engine, "X4U-E-NEW"), (alternator, "A-90B"), (production.lot_producing_id, "MO-NEW")):
            with self.assertRaises(UserError):
                record.with_user(self.storekeeper).name = name
            record.with_user(self.operation).name = name
        self.assertEqual(card.engine_serial, "X4U-E-NEW")
        self.assertEqual(card.alternator_serial, "A-90B")
        self.assertEqual(card.name, "MO-NEW")

    # T33 (P1): the Job Order shows the PI numbers of its sales order, and is found by them
    def test_job_order_shows_its_pi(self):
        order, production = self._sell()
        self.assertFalse(production.x4u_proforma_names)
        self.env["x4u.sale.proforma"].create({"order_id": order.id})
        self.assertEqual(production.x4u_proforma_names, "%s-PI" % order.name)
        found = self.env["mrp.production"].search([("x4u_proforma_names", "ilike", "%s-PI" % order.name)])
        self.assertEqual(found, production)

    # T34 (v0.10 B1-B3): the body goes by its serial too: in at the receipt, out at Deliver Materials,
    # on the card, and the generator is worth that very body
    def test_body_goes_by_serial(self):
        self.assertEqual(self.body_canopy.tracking, "serial")
        self.assertTrue(self.body_canopy.lot_valuated)
        receipt = self._receipt(self.body_canopy, 1)
        receipt.move_ids.quantity = 1
        receipt.move_ids.picked = True
        with self.assertRaises(UserError):
            receipt.button_validate()
        receipt.move_ids.move_line_ids.lot_name = "X4U-BODY-1"
        receipt.button_validate()
        self.template.categ_id = self.env.ref("x4u_setup_base.categ_generators")
        self._stock(self.body_canopy, 1, price=350.0)
        self._stock(self.engine, 1, price=1000.0)
        self._stock(self.alt_stamford, 1, price=500.0)
        _order, production = self._sell()
        # Without its serial the body stays in stock, the Job Order waits for it.
        self._deliver_materials(production, {self.engine: 1, self.alt_stamford: 1})
        self.assertEqual(production.x4u_job_state, "parts_ready")
        dear = self._lots(self.body_canopy).filtered(lambda lot: lot.avg_cost == 350.0)
        self.assertEqual(len(dear), 1)
        self._deliver_materials(production, lots={self.body_canopy: dear})
        self.assertEqual(production.x4u_job_state, "material_delivered")
        card = production.x4u_generator_id
        self.assertEqual((card.x4u_body_lot_id, card.x4u_body_serial), (dear, dear.name))
        dear.with_user(self.operation).name = "X4U-BODY-2B"
        self.assertEqual(card.x4u_body_serial, "X4U-BODY-2B", "the card follows the new serial (E3)")
        self._finish(production)
        finished = production.move_finished_ids.filtered(lambda m: m.product_id == production.product_id)
        self.assertAlmostEqual(sum(finished.stock_valuation_layer_ids.mapped("value")), (1000.0 + 500.0 + 350.0) * 1.2)

    # T35-T36 (v0.10 S1-S2): the Job Order and its generator card are found by any serial of the
    # generator or of its parts, and the card by the PI
    def test_find_by_any_serial(self):
        receipt = self._receipt(self.alt_stamford, 1)
        receipt.move_ids.quantity = 1
        receipt.move_ids.x4u_alternator_serials = "A-55"
        receipt.move_ids.picked = True
        receipt.button_validate()
        for part in (self.engine, self.body_canopy):
            self._stock(part, 1)
        order, production = self._sell()
        action = production.with_user(self.storekeeper).action_x4u_deliver_materials()
        wizard = self.env[action["res_model"]].with_user(self.storekeeper).browse(action["res_id"])
        for line in wizard.line_ids:
            if line.x4u_role == "alternator":
                line.alternator_serial_id = line.available_alternator_ids[:1]
            elif line.tracking == "serial":
                line.lot_id = line.available_lot_ids[:1]
        wizard.action_confirm()
        card = production.x4u_generator_id
        engine, body = card.x4u_engine_lot_id, card.x4u_body_lot_id
        self.assertTrue(engine and body)
        Production = self.env["mrp.production"].with_user(self.salesman)
        Card = self.env["x4u.generator"].with_user(self.salesman)
        for serial in (production.lot_producing_id.name, engine.name, body.name, "A-55"):
            self.assertEqual(Production.search([("x4u_serial_search", "ilike", serial)]), production, serial)
            self.assertEqual(Card.search([("x4u_serial_search", "ilike", serial)]), card, serial)
        self.assertFalse(Production.search([("x4u_serial_search", "ilike", "X4U-NO-SUCH-SERIAL")]))
        self.env["x4u.sale.proforma"].create({"order_id": order.id})
        self.assertEqual(Card.search([("x4u_proforma_search", "ilike", "%s-PI" % order.name)]), card)
