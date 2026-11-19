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
        old_names = {}
        if "name" in vals:
            renamed = self.filtered(lambda lot: lot.name != vals["name"])
            check_edit_serials(self.env, renamed.mapped("name"))
            old_names = {lot.id: lot.name for lot in renamed}
        res = super().write(vals)
        if renamed:
            renamed._x4u_follow_serial(old_names)
        return res

    def _x4u_follow_serial(self, old_names=None):
        """Spec v0.9 E3: the generator card's Engine Serial and Body Serial follow their engine (or
        CKD) and body (the card's own Serial No and the Ready Job Order link the serial, so they
        follow by themselves). Spec v0.12 J9: so does the generator's serial, when it is the engine's."""
        Card = self.env["x4u.generator"].sudo()
        old_names = old_names or {}
        for card in Card.search([("x4u_engine_lot_id", "in", self.ids)]):
            engine = card.x4u_engine_lot_id
            card.engine_serial = engine.name
            if card.lot_id and card.lot_id.name == old_names.get(engine.id):
                card.lot_id.name = engine.name
        for card in Card.search([("x4u_body_lot_id", "in", self.ids)]):
            card.x4u_body_serial = card.x4u_body_lot_id.name
