import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .stock_lot import check_edit_serials


def split_serials(text):
    """'A-77, A-78' or one per line -> ['A-77', 'A-78'], in order, without repeats."""
    names = []
    for name in re.split(r"[,;\n]+", text or ""):
        name = name.strip()
        if name and name not in names:
            names.append(name)
    return names


class X4uAlternatorSerial(models.Model):
    """Spec v0.8.1 N4: an alternator's serial, written at the receipt when it is known (optional),
    so Deliver Materials offers the alternators in stock in a list. Alternators are not tracked by
    serial in the stock itself: Odoo would then ask for one at every receipt and delivery."""

    _name = "x4u.alternator.serial"
    _description = "Alternator Serial"
    # Spec v0.9 E2: a change of the serial is kept in the chatter.
    _inherit = ["mail.thread"]
    _order = "name"
    _check_company_auto = True

    name = fields.Char(string="Serial No", required=True, index="trigram", tracking=True)
    product_id = fields.Many2one("product.product", string="Alternator", required=True, index=True, check_company=True)
    company_id = fields.Many2one("res.company", required=True, index=True, default=lambda self: self.env.company)
    state = fields.Selection([("in_stock", "In Stock"), ("fitted", "Fitted")], default="in_stock", required=True, index=True)
    picking_id = fields.Many2one("stock.picking", string="Received In", readonly=True, copy=False)
    production_id = fields.Many2one("mrp.production", string="Fitted In", readonly=True, copy=False)

    _sql_constraints = [
        ("x4u_alternator_serial_unique", "unique(product_id, name, company_id)", "This alternator serial already exists."),
    ]

    @api.depends("name", "product_id")
    def _compute_display_name(self):
        for serial in self:
            serial.display_name = serial.name

    def write(self, vals):
        renamed = self.browse()
        if "name" in vals:
            renamed = self.filtered(lambda serial: serial.name != vals["name"])
            # Spec v0.9 E1: the Administrator, the General Manager or the Operation Manager only.
            check_edit_serials(self.env, renamed.mapped("name"))
        res = super().write(vals)
        # Spec v0.9 E3: the generator card shows the new serial.
        renamed.filtered("production_id")._x4u_write_on_card()
        return res

    def _x4u_write_on_card(self):
        """The alternator serials fitted in each Job Order, on its generator card."""
        Serial = self.sudo()
        for production in self.sudo().production_id:
            card = production.lot_producing_id.x4u_generator_id
            if card:
                fitted = Serial.search([("production_id", "=", production.id), ("state", "=", "fitted")], order="id")
                card.alternator_serial = " / ".join(fitted.mapped("name")) or False

    @api.model
    def _x4u_register(self, move, names):
        """The serials typed on a receipt line of alternators (spec v0.8.1 N4)."""
        quantity = int(move.product_uom._compute_quantity(move.quantity, move.product_id.uom_id))
        if len(names) > quantity:
            raise UserError(
                _(
                    "%(part)s: %(count)s alternator serials for %(quantity)s received.",
                    part=move.product_id.display_name, count=len(names), quantity=quantity,
                )
            )
        Serial = self.sudo()
        taken = Serial.search([("product_id", "=", move.product_id.id), ("name", "in", names), ("company_id", "=", move.company_id.id)])
        if taken:
            raise UserError(_("These alternator serials are already registered: %s", ", ".join(taken.mapped("name"))))
        return Serial.with_context(mail_create_nolog=True).create(
            [
                {"name": name, "product_id": move.product_id.id, "company_id": move.company_id.id, "picking_id": move.picking_id.id}
                for name in names
            ]
        )
