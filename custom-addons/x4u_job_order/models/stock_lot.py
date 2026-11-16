from odoo import _, fields, models
from odoo.exceptions import UserError

EDIT_SERIALS = "x4u_job_order.group_x4u_edit_serials"


def check_edit_serials(env, names):
    """Spec v0.9 E1: after the receipt, only the Administrator, the General Manager and the
    Operation Manager change a serial (group Edit Serials). The Storekeeper and Purchasing write it
    on the receipt and correct it there before Validate."""
    if names and not env.su and not env.user.has_group(EDIT_SERIALS):
        raise UserError(
            _(
                "Only the Administrator, the General Manager or the Operation Manager can change a serial number (%s).",
                ", ".join(names),
            )
        )


class StockLot(models.Model):
    _inherit = "stock.lot"

    # Spec v0.9 E2: every change in the chatter of the serial: old -> new, who, when.
    name = fields.Char(tracking=True)

    def write(self, vals):
        renamed = self.browse()
        if "name" in vals:
            renamed = self.filtered(lambda lot: lot.name != vals["name"])
            check_edit_serials(self.env, renamed.mapped("name"))
        res = super().write(vals)
        if renamed:
            renamed._x4u_follow_serial()
        return res

    def _x4u_follow_serial(self):
        """Spec v0.9 E3: the generator card's Engine Serial and Body Serial follow their engine (or
        CKD) and body (the card's own Serial No and the Ready Job Order link the serial, so they
        follow by themselves)."""
        Card = self.env["x4u.generator"].sudo()
        for card in Card.search([("x4u_engine_lot_id", "in", self.ids)]):
            card.engine_serial = card.x4u_engine_lot_id.name
        for card in Card.search([("x4u_body_lot_id", "in", self.ids)]):
            card.x4u_body_serial = card.x4u_body_lot_id.name
