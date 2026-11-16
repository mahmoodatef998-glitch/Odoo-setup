from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import X4uJobOrderCommon


@tagged("post_install", "-at_install")
class TestOrderSerials(X4uJobOrderCommon):
    """Spec v0.11: an order of several generators, each with its own serials (D1-D3)."""

    def _sell_two(self, prefix="A"):
        receipt = self._receipt(self.alt_stamford, 2)
        receipt.move_ids.quantity = 2
        receipt.move_ids.x4u_alternator_serials = "%s-1, %s-2" % (prefix, prefix)
        receipt.move_ids.picked = True
        receipt.button_validate()
        for part in (self.engine, self.body_canopy):
            self._stock(part, 2)
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "warehouse_id": self.warehouse.id,
                "order_line": [Command.create({"product_id": self.variant.id, "product_uom_qty": 2})],
            }
        )
        order.action_confirm()
        jobs = order.mrp_production_ids.sorted("id")
        self.assertEqual(len(jobs), 2, "one Job Order per generator (V8)")
        self.engines = self._lots(self.engine).sorted("name")
        self.bodies = self._lots(self.body_canopy).sorted("name")
        names = ("%s-1" % prefix, "%s-2" % prefix)
        self.alternators = self.env["x4u.alternator.serial"].search([("name", "in", names)]).sorted("name")
        return order, jobs

    def _deliver_all(self, jobs):
        action = jobs[0].with_user(self.storekeeper).action_x4u_deliver_order()
        wizard = self.env[action["res_model"]].with_user(self.storekeeper).browse(action["res_id"])
        self.assertEqual(wizard.line_ids.production_id, jobs, "a line per generator of the order")
        for index, line in enumerate(wizard.line_ids.sorted(lambda l: l.production_id.id)):
            line.write(
                {
                    "engine_lot_id": self.engines[index].id,
                    "alternator_serial_id": self.alternators[index].id,
                    "body_lot_id": self.bodies[index].id,
                }
            )
        return wizard

    # T38 (D1): the generators of the order in one screen; one serial is not chosen for two
    def test_deliver_all_generators(self):
        _order, jobs = self._sell_two()
        self.assertEqual(jobs[0].x4u_order_open_jobs, 2)
        wizard = self._deliver_all(jobs)
        first, second = wizard.line_ids.sorted(lambda l: l.production_id.id)
        second.engine_lot_id = first.engine_lot_id
        with self.assertRaises(UserError):
            wizard.action_confirm()
        second.engine_lot_id = self.engines[1]
        wizard.action_confirm()
        for index, job in enumerate(jobs):
            self.assertEqual(job.x4u_job_state, "material_delivered", job.name)
            card = job.x4u_generator_id
            self.assertEqual(card.x4u_engine_lot_id, self.engines[index])
            self.assertEqual(card.x4u_body_lot_id, self.bodies[index])
            self.assertEqual(card.alternator_serial, self.alternators[index].name)
        # The list button gives the same screen for the Job Orders selected.
        _order2, jobs2 = self._sell_two("B")
        action = jobs2.with_user(self.storekeeper).action_x4u_deliver_all()
        self.assertEqual(self.env[action["res_model"]].browse(action["res_id"]).line_ids.production_id, jobs2)

    # T39 (D2): at Finish the factory's real serials: the first generator got the second one's engine
    # and alternator, so the second one takes the first one's; the canopy is required
    def test_finish_swaps_with_the_other_generator(self):
        _order, (job_a, job_b) = self._sell_two()
        self._deliver_all(job_a | job_b).action_confirm()
        action = job_a.with_user(self.operation).action_x4u_finish()
        wizard = self.env[action["res_model"]].with_user(self.operation).browse(action["res_id"])
        self.assertEqual(
            (wizard.engine_lot_id, wizard.body_lot_id, wizard.alternator_serial_id),
            (self.engines[0], self.bodies[0], self.alternators[0]),
            "filled with what was delivered",
        )
        self.assertIn(self.engines[1], wizard.available_engine_lot_ids, "any engine in the factory")
        wizard.body_lot_id = False
        with self.assertRaises(UserError):
            wizard.action_confirm()
        wizard.write({"body_lot_id": self.bodies[0].id, "engine_lot_id": self.engines[1].id, "alternator_serial_id": self.alternators[1].id})
        wizard.action_confirm()
        self.assertEqual(job_a.state, "done")
        engine_a = job_a.move_raw_ids.filtered(lambda m: m.x4u_role == "engine")
        self.assertEqual(engine_a.move_line_ids.lot_id, self.engines[1])
        card_a, card_b = job_a.x4u_generator_id, job_b.x4u_generator_id
        self.assertEqual((card_a.x4u_engine_lot_id, card_a.alternator_serial), (self.engines[1], "A-2"))
        self.assertEqual((card_b.x4u_engine_lot_id, card_b.alternator_serial), (self.engines[0], "A-1"), "B takes A's")
        self._finish(job_b)
        self.assertEqual(job_b.state, "done")
        engine_b = job_b.move_raw_ids.filtered(lambda m: m.x4u_role == "engine")
        self.assertEqual(engine_b.move_line_ids.lot_id, self.engines[0])

    # T40 (D3): the serials of each generator on the delivery note, the tax invoice and the sales order
    def test_serials_on_the_documents(self):
        order, jobs = self._sell_two()
        self._deliver_all(jobs).action_confirm()
        for job in jobs:
            self._finish(job)
        self._deliver(order)
        delivery = order.picking_ids.filtered(lambda p: p.picking_type_code == "outgoing")
        invoice = order._create_invoices()
        Report = self.env["ir.actions.report"]
        for report, record in (
            ("stock.action_report_delivery", delivery),
            ("account.account_invoices", invoice),
            ("sale.action_report_saleorder", order),
        ):
            html = Report._render_qweb_html(report, record.ids)[0]
            self.assertIn(b"Generator Serial Numbers", html, report)
            for serial in (jobs[0].lot_producing_id.name, self.engines[1].name, self.bodies[0].name, "A-2"):
                self.assertIn(serial.encode(), html, "%s on %s" % (serial, report))
