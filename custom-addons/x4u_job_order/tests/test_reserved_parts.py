from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import X4uJobOrderCommon


@tagged("post_install", "-at_install")
class TestReservedParts(X4uJobOrderCommon):
    """Spec v0.6 R1-R4: parts reserved for other Job Orders, priorities, and no double buying."""

    def _stock_one_set(self):
        for part in (self.engine, self.alt_stamford, self.body_canopy):
            self.env["stock.quant"]._update_available_quantity(part, self.warehouse.lot_stock_id, 1)

    def _open(self, production, user):
        action = production.with_user(user).action_x4u_reserved_parts()
        return self.env[action["res_model"]].with_user(user).browse(action["res_id"])

    # R1-R2: the Operation Manager gives the parts of MO-A to MO-B; MO-A waits and is requested again
    def test_take_parts_from_another_job_order(self):
        self._stock_one_set()
        _order_a, job_a = self._sell()
        self.assertEqual(job_a.x4u_job_state, "parts_ready")
        self.assertFalse(job_a._x4u_purchase_requests(), "everything came from stock: nothing to buy")
        _order_b, job_b = self._sell()
        self.assertEqual(job_b.x4u_material_flag, "missing")
        requests_b = job_b._x4u_purchase_requests()
        self.assertEqual(requests_b.state, "approved")

        wizard = self._open(job_b, self.storekeeper)
        self.assertEqual(len(wizard.line_ids), 3, "the Storekeeper sees who holds the 3 parts")
        self.assertEqual(wizard.line_ids.donor_production_id, job_a)
        self.assertEqual(set(wizard.line_ids.mapped("customer")), {self.customer.display_name})
        self.assertFalse(wizard.can_move)
        wizard.line_ids.selected = True
        with self.assertRaises(UserError):
            wizard.action_take()

        wizard = self._open(job_b, self.operation)
        self.assertTrue(wizard.can_move)
        wizard.line_ids.selected = True
        wizard.action_take()

        self.assertEqual(job_b.x4u_job_state, "parts_ready")
        self.assertEqual(job_b.x4u_material_flag, "ready")
        # R4: MO-B got its parts from stock, so its request is closed (OCA rejects it).
        self.assertTrue(all(requests_b.line_ids.mapped("cancelled")))
        self.assertEqual(requests_b.state, "rejected")
        # MO-A waits, and its parts are requested.
        self.assertEqual(job_a.x4u_job_state, "waiting_parts")
        self.assertEqual(job_a.x4u_material_flag, "missing")
        requests_a = job_a._x4u_purchase_requests()
        self.assertEqual(requests_a.state, "approved")
        self.assertEqual(len(requests_a.line_ids.filtered(lambda line: not line.cancelled)), 3)
        self.assertTrue(any("taken from %s" % job_a.name in (body or "") for body in job_b.message_ids.mapped("body")))
        self.assertTrue(any("given to %s" % job_b.name in (body or "") for body in job_a.message_ids.mapped("body")))

    # R4: the parts arrive in stock after the request: the request closes and cannot be bought
    def test_request_closed_when_stock_covers_it(self):
        _order, job = self._sell()
        requests = job._x4u_purchase_requests()
        self.assertEqual(len(requests.line_ids), 3)
        self._stock_one_set()
        job._x4u_pick_components().action_assign()
        self.assertEqual(job.x4u_job_state, "parts_ready")
        self.assertTrue(all(requests.line_ids.mapped("cancelled")))
        self.assertEqual(requests.state, "rejected")
        self.assertEqual(set(job.move_raw_ids.mapped("x4u_part_status")), {"from_stock"})
        Wizard = self.env["purchase.request.line.make.purchase.order"]
        with self.assertRaises(UserError):
            Wizard.with_context(active_model="purchase.request.line", active_ids=requests.line_ids.ids).create(
                {"supplier_id": self.vendor_engine.id}
            )

    # R3: every other order comes first: buy new parts for this one
    def test_buy_new_parts(self):
        self._stock_one_set()
        _order_a, job_a = self._sell()
        _order_b, job_b = self._sell()
        wizard = self._open(job_b, self.operation)
        action = wizard.action_buy()
        self.assertEqual(action["res_model"], "purchase.request")
        self.assertEqual(job_a.x4u_job_state, "parts_ready", "nobody's parts moved")
        lines = job_b._x4u_purchase_requests().line_ids
        self.assertEqual(len(lines.filtered(lambda line: not line.cancelled)), 3)
        with self.assertRaises(UserError):
            self._open(job_b, self.storekeeper).action_buy()
