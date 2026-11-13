from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import X4uJobOrderCommon


@tagged("post_install", "-at_install")
class TestFreeParts(X4uJobOrderCommon):
    """Spec v0.8: every engine by its serial (N1-N6), Job Order parts free in stock (F1-F6)."""

    def _sell_many(self, count):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "warehouse_id": self.warehouse.id,
                "order_line": [Command.create({"product_id": self.variant.id, "product_uom_qty": count})],
            }
        )
        order.action_confirm()
        return order, order.mrp_production_ids.sorted("id")

    def _wizard(self, production):
        action = production.with_user(self.storekeeper).action_x4u_deliver_materials()
        return self.env[action["res_model"]].with_user(self.storekeeper).browse(action["res_id"])

    # T21 (N1): engines are tracked and valued by serial; they come in with one serial each
    def test_engines_go_by_serial(self):
        self.assertEqual(self.engine.tracking, "serial")
        self.assertTrue(self.engine.lot_valuated)
        self.assertEqual(self.alt_stamford.tracking, "none", "the alternator serial is optional (N4)")
        with self.assertRaises(ValidationError):
            self.engine.product_tmpl_id.tracking = "none"
        receipt = self._receipt(self.engine, 1)
        receipt.move_ids.quantity = 1
        receipt.move_ids.picked = True
        with self.assertRaises(UserError):
            receipt.button_validate()
        receipt.move_ids.move_line_ids.lot_name = "X4U-E-1001"
        receipt.button_validate()
        self.assertEqual(receipt.state, "done")
        self.assertEqual(self._lots(self.engine).mapped("name"), ["X4U-E-1001"])

    # T22 (F1, F2, F4): two Job Orders and one engine: both green, nothing reserved;
    # the newer one is delivered first and the older one goes back to red
    def test_newer_job_order_takes_the_engine_first(self):
        for part in (self.engine, self.alt_stamford, self.body_canopy):
            self._stock(part, 1)
        _order, (job_a, job_b) = self._sell_many(2)
        self.assertEqual((job_a.x4u_job_state, job_b.x4u_job_state), ("parts_ready", "parts_ready"))
        self.assertEqual((job_a.x4u_material_flag, job_b.x4u_material_flag), ("ready", "ready"))
        self.assertFalse((job_a | job_b)._x4u_pick_components().move_ids.move_line_ids, "nothing is reserved")
        self.assertFalse(
            (job_a | job_b).activity_ids.filtered(lambda a: "Deliver the material" in (a.summary or "")),
            "the Storekeeper delivers the Job Order you choose, no to-do",
        )
        self._deliver_materials(job_b)
        self.assertEqual(job_b.x4u_job_state, "material_delivered")
        self.assertEqual(job_a.x4u_job_state, "waiting_parts")
        self.assertEqual(job_a.x4u_material_flag, "missing")
        # New parts arrive: the older Job Order is green again.
        for part in (self.engine, self.alt_stamford, self.body_canopy):
            self._stock(part, 1)
        self.assertEqual(job_a.x4u_job_state, "parts_ready")

    # T23 (N3-N5): Deliver Materials needs the engine serial; the card gets it, and the
    # alternator serial when it is written
    def test_deliver_materials_needs_the_engine_serial(self):
        for part in (self.engine, self.alt_stamford, self.body_canopy):
            self._stock(part, 1)
        self._stock(self.engine, 1)
        _order, production = self._sell()
        wizard = self._wizard(production)
        engine_line = wizard.line_ids.filtered(lambda line: line.x4u_role == "engine")
        self.assertEqual(engine_line.quantity, 0, "nothing proposed: the Storekeeper picks the serial")
        self.assertEqual(len(engine_line.available_lot_ids), 2)
        engine_line.quantity = 1
        with self.assertRaises(UserError):
            wizard.action_confirm()
        self.assertEqual(production.x4u_job_state, "parts_ready")
        lot = engine_line.available_lot_ids.sorted("name")[-1]
        engine_line.lot_ids = lot
        wizard.line_ids.filtered(lambda line: line.x4u_role == "alternator").alternator_serial = "A-77"
        wizard.action_confirm()
        self.assertEqual(production.x4u_job_state, "material_delivered")
        card = production.x4u_generator_id
        self.assertEqual(card.x4u_engine_lot_id, lot)
        self.assertEqual(card.engine_serial, lot.name)
        self.assertEqual(card.alternator_serial, "A-77")
        production.with_user(self.operation).action_x4u_finish()
        engine = production.move_raw_ids.filtered(lambda move: move.x4u_role == "engine")
        self.assertEqual(engine.move_line_ids.lot_id, lot, "the factory fits the engine delivered")
        self.assertEqual(card.x4u_engine_lot_id, lot)

    # T23b (N4): without an alternator serial the Job Order goes on
    def test_alternator_serial_is_optional(self):
        for part in (self.engine, self.alt_stamford, self.body_canopy):
            self._stock(part, 1)
        _order, production = self._sell()
        self._deliver_materials(production)
        self.assertEqual(production.x4u_job_state, "material_delivered")
        self.assertFalse(production.x4u_generator_id.alternator_serial)

    # T24 (N6): the generator is worth the very engine fitted in it
    def test_generator_worth_its_own_engine(self):
        self.template.categ_id = self.env.ref("x4u_setup_base.categ_generators")
        self._stock(self.engine, 1, price=1000.0)
        self._stock(self.engine, 1, price=1400.0)
        self._stock(self.alt_stamford, 1, price=500.0)
        self._stock(self.body_canopy, 1, price=300.0)
        _order, production = self._sell()
        dear = self._lots(self.engine).filtered(lambda lot: lot.avg_cost == 1400.0)
        self.assertEqual(len(dear), 1)
        self._deliver_materials(production, lots={self.engine: dear})
        production.with_user(self.operation).action_x4u_finish()
        finished = production.move_finished_ids.filtered(lambda m: m.product_id == production.product_id)
        self.assertAlmostEqual(sum(finished.stock_valuation_layer_ids.mapped("value")), (1400.0 + 500.0 + 300.0) * 1.2)

    # T25 (F3): five Job Orders and one engine in stock: four engines are requested, five alternators
    def test_buy_only_what_stock_does_not_cover(self):
        self._stock(self.engine, 1)
        _order, jobs = self._sell_many(5)
        self.assertEqual(len(jobs), 5)
        lines = jobs._x4u_purchase_requests().line_ids
        self.assertEqual(sum(lines.filtered(lambda line: line.product_id == self.engine).mapped("product_qty")), 4)
        self.assertEqual(sum(lines.filtered(lambda line: line.product_id == self.alt_stamford).mapped("product_qty")), 5)
