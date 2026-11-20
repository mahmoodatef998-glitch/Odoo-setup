from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from odoo.addons.x4u_job_order.tests.common import X4uJobOrderCommon


@tagged("post_install", "-at_install")
class TestRoleCycle(X4uJobOrderCommon):
    """The cycle with the real 4U roles, not test users with loose groups (2026-11-20: the
    Purchasing Officer could not make an RFQ from a material request)."""

    def _role_user(self, role, login):
        user = new_test_user(self.env, login=login, groups="base.group_user")
        user.write({"role_line_ids": [Command.create({"role_id": self.env.ref("x4u_roles." + role).id})]})
        return user

    def test_purchasing_officer_makes_the_rfq(self):
        officer = self._role_user("role_purchasing_officer", "x4u_rc_purchasing")
        _order, production = self._sell()
        lines = production._x4u_purchase_requests().line_ids.filtered(lambda line: not line.cancelled)
        self.assertTrue(lines, "nothing in stock: the parts are requested")
        wizard = (
            self.env["purchase.request.line.make.purchase.order"]
            .with_user(officer)
            .with_context(active_model="purchase.request.line", active_ids=lines.ids)
            .create({"supplier_id": self.vendor_engine.id})
        )
        wizard.make_purchase_order()
        po = self.env["purchase.order"].search([("order_line.purchase_request_lines", "in", lines.ids)])
        self.assertEqual(len(po), 1)
        po.with_user(officer).button_confirm()
        self.assertIn(po.state, ("to approve", "purchase"))
        # Still Receipts Only: no hand edit of the Job Order's own transfers.
        pick_move = production._x4u_component_moves()[:1]
        with self.assertRaises(AccessError):
            pick_move.with_user(officer).write({"date_deadline": fields.Datetime.now()})
