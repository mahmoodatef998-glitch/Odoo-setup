from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged

from .common import X4uJobOrderCommon


@tagged("post_install", "-at_install")
class TestOrderJob(X4uJobOrderCommon):
    """Spec v0.12: one Job Order for the sales order, a row per generator on its Serial tab (J1-J10)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ptavs = cls.template.attribute_line_ids.product_template_value_ids

        def ptav(xmlid):
            return ptavs.filtered(lambda v: v.product_attribute_value_id == cls.env.ref("x4u_setup_base." + xmlid))

        # A second model: the open generator (another body).
        cls.variant_open = cls.template._create_product_variant(ptav("attr_enclosure_open") + ptav("attr_alternator_stamford"))

    def _order(self, lines):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "warehouse_id": self.warehouse.id,
                "order_line": [Command.create(values) for values in lines],
            }
        )
        order.action_confirm()
        return order

    def _sell_two(self):
        """Two generators of one model, their parts in stock: engines, canopies and alternators by serial."""
        receipt = self._receipt(self.alt_stamford, 2)
        receipt.move_ids.quantity = 2
        receipt.move_ids.x4u_alternator_serials = "J-1, J-2"
        receipt.move_ids.picked = True
        receipt.button_validate()
        for part in (self.engine, self.body_canopy):
            self._stock(part, 2)
        order = self._order([{"product_id": self.variant.id, "product_uom_qty": 2}])
        job = order.x4u_job_ids
        self.engines = self._lots(self.engine).sorted("name")
        self.bodies = self._lots(self.body_canopy).sorted("name")
        self.alternators = self.env["x4u.alternator.serial"].search([("name", "in", ("J-1", "J-2"))]).sorted("name")
        return order, job, job.production_ids.sorted("name")

    def _deliver_job(self, job, rows):
        """Deliver Materials from the Job Order as the Storekeeper; `rows` = {production: (engine, body, alternator)}."""
        action = job.with_user(self.storekeeper).action_deliver_materials()
        wizard = self.env[action["res_model"]].with_user(self.storekeeper).browse(action["res_id"])
        for line in wizard.line_ids:
            if line.production_id in rows:
                engine, body, alternator = rows[line.production_id]
                line.write({"engine_lot_id": engine.id, "body_lot_id": body.id, "alternator_serial_id": alternator.id})
        wizard.action_confirm()
        return wizard

    # T41 (J1, J2, J5, J7, J8): two models in one order: one Job Order, a generator each inside it
    def test_one_job_order_for_the_order(self):
        order = self._order(
            [
                {"product_id": self.variant.id, "product_uom_qty": 2},
                {"product_id": self.variant_open.id, "product_uom_qty": 1},
            ]
        )
        job = order.x4u_job_ids
        self.assertEqual(len(job), 1, "one Job Order for the sales order")
        self.assertRegex(job.name, r"^MO\d{3,}$")
        productions = job.production_ids.sorted("name")
        self.assertEqual(productions, order.mrp_production_ids)
        self.assertEqual(productions.mapped("name"), ["%s/%s" % (job.name, n) for n in (1, 2, 3)])
        self.assertEqual(productions.product_id, self.variant | self.variant_open)
        self.assertEqual((job.state, job.generator_count, job.material_flag), ("waiting_parts", 3, "missing"))
        self.assertEqual(job.progress, "Finished 0 / 3 · Delivered 0 / 3")
        self.assertIn("2 × %s" % self.variant.display_name, job.models_summary)
        # One analytic account for the order, on both lines.
        account = job.analytic_account_id
        self.assertTrue(account)
        self.assertEqual(account.code, job.name)
        self.assertEqual(productions.x4u_analytic_account_id, account)
        for line in order.order_line:
            self.assertEqual(line.analytic_distribution, {str(account.id): 100.0})
        # Found by its PI, by a generator serial and by the model.
        self.env["x4u.sale.proforma"].create({"order_id": order.id})
        Job = self.env["x4u.job.order"].with_user(self.salesman)
        self.assertEqual(Job.search([("proforma_names", "ilike", "%s-PI" % order.name)]), job)
        self.assertEqual(Job.search([("serial_search", "=", productions[0].lot_producing_id.name)]), job)
        self.assertEqual(Job.search([("production_ids.product_id", "=", self.variant_open.id)]), job)
        # The slowest generator: the canopy ones get their parts, the open one still waits.
        for part, qty in ((self.engine, 3), (self.alt_stamford, 3), (self.body_canopy, 2)):
            self._stock(part, qty)
        self.assertEqual(set(productions.filtered(lambda p: p.product_id == self.variant).mapped("x4u_job_state")), {"parts_ready"})
        self.assertEqual((job.state, job.material_flag), ("waiting_parts", "missing"))

    # T42 (J3, J4): the Operation Manager picks the serials on the Serial tab; Deliver Materials gets them
    def test_serial_tab(self):
        _order, job, (job_a, job_b) = self._sell_two()
        with Form(job.with_user(self.operation)) as form:
            with form.production_ids.edit(list(job.production_ids).index(job_a)) as row:
                row.x4u_engine_lot_id = self.engines[0]
                row.x4u_body_lot_id = self.bodies[0]
                row.x4u_alternator_id = self.alternators[0]
        self.assertEqual(
            (job_a.x4u_engine_lot_id, job_a.x4u_body_lot_id, job_a.x4u_alternator_id),
            (self.engines[0], self.bodies[0], self.alternators[0]),
        )
        self.assertNotIn(self.engines[0], job_b.with_user(self.operation).x4u_engine_lot_ids, "chosen for the other generator")
        with self.assertRaises(UserError):
            job_b.with_user(self.operation).write({"x4u_engine_lot_id": self.engines[0].id})
        with self.assertRaises(UserError):
            job_b.with_user(self.operation).write({"x4u_engine_lot_id": self.bodies[1].id})
        with self.assertRaises(AccessError):
            job_b.with_user(self.storekeeper).write({"x4u_engine_lot_id": self.engines[1].id})
        # Deliver Materials of the Job Order: a line per generator, filled with the Serial tab.
        action = job.with_user(self.storekeeper).action_deliver_materials()
        wizard = self.env[action["res_model"]].with_user(self.storekeeper).browse(action["res_id"])
        self.assertEqual(wizard.line_ids.production_id, job_a | job_b)
        line_a = wizard.line_ids.filtered(lambda line: line.production_id == job_a)
        self.assertEqual(
            (line_a.engine_lot_id, line_a.body_lot_id, line_a.alternator_serial_id),
            (self.engines[0], self.bodies[0], self.alternators[0]),
        )
        wizard.line_ids.filtered(lambda line: line.production_id == job_b).write(
            {"engine_lot_id": self.engines[1].id, "body_lot_id": self.bodies[1].id, "alternator_serial_id": self.alternators[1].id}
        )
        wizard.action_confirm()
        self.assertEqual(set((job_a | job_b).mapped("x4u_job_state")), {"material_delivered"})
        self.assertEqual(job.state, "material_delivered")
        self.assertEqual(job_b.x4u_alternator_id, self.alternators[1], "the row shows what was delivered")
        # Once delivered, a serial changes at Finish only.
        self.assertFalse(job_a.with_user(self.operation).x4u_serials_editable)
        with self.assertRaises(UserError):
            job_a.with_user(self.operation).write({"x4u_body_lot_id": self.bodies[1].id})

    # T43 (J9): the generator takes its engine's serial; a swap at Finish swaps them; a renamed engine renames it
    def test_generator_serial_is_the_engine(self):
        _order, job, (job_a, job_b) = self._sell_two()
        self.assertEqual(job_a.lot_producing_id.name, job_a.name, "its Job Order number until the engine is delivered")
        self._deliver_job(
            job,
            {
                job_a: (self.engines[0], self.bodies[0], self.alternators[0]),
                job_b: (self.engines[1], self.bodies[1], self.alternators[1]),
            },
        )
        self.assertEqual(job_a.lot_producing_id.name, self.engines[0].name)
        self.assertEqual(job_a.x4u_generator_id.name, self.engines[0].name, "and its card")
        self.assertEqual(job_b.x4u_generator_serial, self.engines[1].name)
        # The factory fitted B's engine in A: A takes it, B takes A's.
        action = job_a.with_user(self.operation).action_x4u_finish()
        wizard = self.env[action["res_model"]].with_user(self.operation).browse(action["res_id"])
        wizard.engine_lot_id = self.engines[1]
        wizard.action_confirm()
        self.assertEqual(job_a.state, "done")
        self.assertEqual(job_a.lot_producing_id.name, self.engines[1].name)
        self.assertEqual(job_b.lot_producing_id.name, self.engines[0].name)
        self.assertEqual(job_b.x4u_engine_lot_id, self.engines[0])
        # E1: the engine serial corrected after the receipt: the generator's follows.
        self.engines[0].name = "X4U-E-RENAMED"
        self.assertEqual(job_b.lot_producing_id.name, "X4U-E-RENAMED")
        self.assertEqual(job_b.x4u_generator_id.engine_serial, "X4U-E-RENAMED")

    # T44 (J4): Finish on the Job Order: a line per generator delivered, all into stock by their engines
    def test_finish_from_the_job_order(self):
        _order, job, (job_a, job_b) = self._sell_two()
        self._deliver_job(
            job,
            {
                job_a: (self.engines[0], self.bodies[0], self.alternators[0]),
                job_b: (self.engines[1], self.bodies[1], self.alternators[1]),
            },
        )
        self.assertTrue(job.can_finish)
        action = job.with_user(self.operation).action_finish()
        wizard = self.env[action["res_model"]].with_user(self.operation).browse(action["res_id"])
        line_a, line_b = wizard.line_ids.sorted(lambda line: line.production_id.name)
        self.assertEqual((line_a.engine_lot_id, line_b.engine_lot_id), (self.engines[0], self.engines[1]))
        line_b.engine_lot_id = self.engines[0]
        with self.assertRaises(UserError):
            wizard.action_confirm()
        line_b.engine_lot_id = self.engines[1]
        wizard.action_confirm()
        self.assertEqual(set((job_a | job_b).mapped("state")), {"done"})
        self.assertEqual((job.state, job.finished_count), ("finished", 2))
        self.assertEqual(
            sorted((job_a | job_b).lot_producing_id.mapped("name")), sorted(self.engines.mapped("name"))
        )
        quants = self.env["stock.quant"].search(
            [("lot_id", "in", (job_a | job_b).lot_producing_id.ids), ("location_id", "=", self.warehouse.lot_stock_id.id)]
        )
        self.assertEqual(sum(quants.mapped("quantity")), 2.0, "both in WH/Stock by their engine serials")

    # T45 (J2, J10): a ready generator is a row of the same Job Order, and comes in with its engine's serial
    def test_ready_generator_in_the_job_order(self):
        order = self._order(
            [
                {"product_id": self.variant.id, "product_uom_qty": 1, "x4u_supply": "assemble"},
                {"product_id": self.variant_open.id, "product_uom_qty": 1, "x4u_supply": "ready"},
            ]
        )
        job = order.x4u_job_ids
        ready = order.x4u_ready_order_ids
        self.assertEqual(len(job), 1)
        self.assertEqual((len(job.production_ids), job.ready_order_ids), (1, ready))
        self.assertEqual(ready.analytic_account_id, job.analytic_account_id)
        self.assertEqual((job.generator_count, job.state), (2, "waiting_parts"))
        lines = ready.request_id.line_ids
        self.env["purchase.request.line.make.purchase.order"].with_context(
            active_model="purchase.request.line", active_ids=lines.ids
        ).create({"supplier_id": self.vendor_engine.id}).make_purchase_order()
        po = self.env["purchase.order"].search([("order_line.purchase_request_lines", "in", lines.ids)])
        po.with_user(self.manager).button_confirm()
        if po.state == "to approve":
            po.with_user(self.manager).button_approve()
        self._validate(po.picking_ids)
        self.assertEqual(ready.state, "in_stock")
        self.assertEqual(ready.lot_id.name, "X4U-E-%s" % ready.name, "the serial of its engine")
        self.assertEqual(job.finished_count, 1)
        self.assertEqual(self.env["x4u.job.order"].search([("serial_search", "=", ready.lot_id.name)]), job)
