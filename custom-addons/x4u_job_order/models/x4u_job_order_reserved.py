from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .mrp_production import JOB_STATES

# Spec v0.6 R1: who changes the priority between Job Orders (Operation Manager and General
# Manager; the Storekeeper only sees who holds the parts).
MOVE_PARTS_GROUP = "mrp.group_mrp_user"


def _short(moves):
    return moves.filtered(
        lambda move: move.state not in ("done", "cancel", "assigned") and move.quantity < move.product_uom_qty
    )


class X4uJobOrderReserved(models.TransientModel):
    """Reserved for Other Orders (spec v0.6 R1-R3): a Job Order is short of a part that is in
    stock but reserved for other Job Orders. The manager sees who holds it and either takes it
    (that order waits and its part is bought again) or buys new parts."""

    _name = "x4u.job.order.reserved"
    _description = "Parts Reserved for Other Job Orders"

    production_id = fields.Many2one("mrp.production", string="Job Order", required=True, readonly=True)
    line_ids = fields.One2many("x4u.job.order.reserved.line", "wizard_id", string="Held By")
    can_move = fields.Boolean(compute="_compute_can_move")

    def _compute_can_move(self):
        allowed = self.env.user.has_group(MOVE_PARTS_GROUP)
        for wizard in self:
            wizard.can_move = allowed

    def _x4u_short_moves(self):
        return _short(self.production_id.sudo()._x4u_pick_components().move_ids)

    def action_take(self):
        """Move the reservation of the ticked lines to this Job Order."""
        self.ensure_one()
        if not self.env.user.has_group(MOVE_PARTS_GROUP):
            raise UserError(_("Only the Operation Manager or the General Manager can move parts between Job Orders."))
        selected = self.line_ids.filtered("selected")
        if not selected:
            raise UserError(_("Tick the Job Order to take the part from."))
        receiver = self.production_id.sudo()
        given = self.env["stock.move"].sudo()
        for line in selected:
            target = self._x4u_short_moves().filtered(lambda move, p=line.product_id: move.product_id == p)[:1]
            donor_move = line.donor_move_id.sudo()
            if not target or donor_move.state not in ("assigned", "partially_available"):
                continue
            donor_move._do_unreserve()
            target._action_assign()
            # What this order did not need goes back to the donor.
            donor_move._action_assign()
            given |= donor_move
            donor = line.donor_production_id.sudo()
            part = line.product_id.display_name
            receiver.message_post(
                body=_("%(part)s taken from %(donor)s by %(user)s.", part=part, donor=donor.name, user=self.env.user.name)
            )
            donor.message_post(
                body=_(
                    "%(part)s given to %(receiver)s by %(user)s: this Job Order waits, and the part is requested again.",
                    part=part, receiver=receiver.name, user=self.env.user.name,
                )
            )
        if not given:
            raise UserError(_("Nothing could be moved: the ticked parts are no longer reserved there."))
        donors = self.env["mrp.production"].sudo()._x4u_from_moves(given)
        for donor in donors:
            if donor.x4u_job_state == "parts_ready" and not all(
                move.state in ("assigned", "done") for move in donor._x4u_component_moves()
            ):
                donor._x4u_set_state("waiting_parts")
        if given._x4u_reopen_requests():
            donors._x4u_notify("purchase", _("Order again the parts given to %s", receiver.name))
        return {"type": "ir.actions.act_window_close"}

    def action_buy(self):
        """All the other orders come first: buy the missing parts for this Job Order."""
        self.ensure_one()
        if not self.env.user.has_group(MOVE_PARTS_GROUP):
            raise UserError(_("Only the Operation Manager or the General Manager can ask to buy new parts here."))
        receiver = self.production_id.sudo()
        short = self._x4u_short_moves()
        if not short:
            raise UserError(_("%s is not missing any part.", receiver.name))
        short._x4u_reopen_requests()
        receiver._x4u_notify("purchase", _("Order the material for %s", receiver.name))
        receiver.message_post(
            body=_(
                "%(user)s chose to buy new parts: %(parts)s.",
                user=self.env.user.name, parts=", ".join(short.product_id.mapped("display_name")),
            )
        )
        return self.production_id.action_x4u_open_requests()


class X4uJobOrderReservedLine(models.TransientModel):
    _name = "x4u.job.order.reserved.line"
    _description = "Part Reserved for Another Job Order"
    _order = "promised_date, donor_production_id"

    wizard_id = fields.Many2one("x4u.job.order.reserved", required=True, ondelete="cascade")
    selected = fields.Boolean(string="Take")
    donor_move_id = fields.Many2one("stock.move", required=True, readonly=True)
    donor_production_id = fields.Many2one("mrp.production", string="Held By", readonly=True)
    product_id = fields.Many2one("product.product", string="Part", readonly=True)
    quantity = fields.Float(string="Reserved", digits="Product Unit of Measure", readonly=True)
    needed = fields.Float(string="This Order Needs", digits="Product Unit of Measure", readonly=True)
    # Copied with sudo when the screen opens: the Storekeeper does not read sales.
    customer = fields.Char(readonly=True)
    sale_order = fields.Char(string="Sales Order", readonly=True)
    promised_date = fields.Datetime(string="Promised Delivery", readonly=True)
    job_state = fields.Selection(JOB_STATES, string="Status", readonly=True)
    confirmed_on = fields.Datetime(string="Job Order Since", readonly=True)

    @api.model
    def _x4u_lines_for(self, production):
        """One line per Job Order and part that holds stock this Job Order is short of."""
        production = production.sudo()
        Move = self.env["stock.move"].sudo()
        Production = self.env["mrp.production"].sudo()
        values = []
        for move in _short(production._x4u_pick_components().move_ids):
            holders = Move.search(
                [
                    ("product_id", "=", move.product_id.id),
                    ("location_id", "=", move.location_id.id),
                    ("picking_type_id", "=", move.picking_type_id.id),
                    ("state", "in", ("assigned", "partially_available")),
                    ("id", "!=", move.id),
                ]
            ).filtered(lambda m: m.quantity > 0)
            for holder in holders:
                donor = Production._x4u_from_moves(holder)[:1]
                if not donor or donor == production or donor.x4u_job_state in ("delivered", "cancelled"):
                    continue
                sale = donor.x4u_sale_order_id
                values.append(
                    {
                        "donor_move_id": holder.id,
                        "donor_production_id": donor.id,
                        "product_id": move.product_id.id,
                        "quantity": holder.quantity,
                        "needed": move.product_uom_qty - move.quantity,
                        "customer": donor.x4u_customer_id.display_name or False,
                        "sale_order": sale.name or False,
                        "promised_date": sale.commitment_date or donor.date_deadline or False,
                        "job_state": donor.x4u_job_state,
                        "confirmed_on": donor.date_start,
                    }
                )
        return values
