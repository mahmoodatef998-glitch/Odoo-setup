from odoo import _, api, fields, models
from odoo.exceptions import UserError


class X4uJobOrderShip(models.TransientModel):
    """Deliver Generators (spec v0.13 L2): the Storekeeper picks the generators of the Job Order
    that leave now on a Delivery Note. Paid before delivery, the goods delivered stay within what
    was paid on the PI (L1); the others leave later, or with the tax invoice (L4)."""

    _name = "x4u.job.order.ship"
    _description = "Deliver Generators"

    job_id = fields.Many2one("x4u.job.order", string="Job Order", required=True, readonly=True)
    order_id = fields.Many2one(related="job_id.sale_order_id", string="Sales Order")
    currency_id = fields.Many2one(related="job_id.sale_order_id.currency_id")
    line_ids = fields.One2many("x4u.job.order.ship.line", "wizard_id", string="Generators")
    limited = fields.Boolean(string="Within Paid", compute="_compute_amounts")
    amount_paid = fields.Monetary(string="Paid", compute="_compute_amounts")
    amount_delivered = fields.Monetary(string="Delivered Before", compute="_compute_amounts")
    amount_selected = fields.Monetary(string="Selected", compute="_compute_amounts")
    amount_left = fields.Monetary(string="Can Still Deliver", compute="_compute_amounts")

    @api.model
    def _x4u_action(self, job):
        order = job.sale_order_id
        if not order:
            raise UserError(_("%s has no sales order to deliver to.", job.name))
        lots = order.sudo()._x4u_generator_lots_in_stock()
        if not lots:
            raise UserError(_("%s has no finished generator in stock to deliver.", job.name))
        wizard = self.create(
            {"job_id": job.id, "line_ids": [fields.Command.create({"lot_id": lot.id}) for lot in lots.sorted("name")]}
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Deliver Generators · %s", job.name),
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.depends("line_ids.selected", "line_ids.amount")
    def _compute_amounts(self):
        for wizard in self:
            order = wizard.order_id.sudo()
            limited = bool(order) and order._x4u_delivery_within_paid()
            wizard.limited = limited
            wizard.amount_paid = order._x4u_amount_received() if order else 0.0
            wizard.amount_delivered = order._x4u_delivered_value() if order else 0.0
            wizard.amount_selected = sum(wizard.line_ids.filtered("selected").mapped("amount"))
            wizard.amount_left = max(wizard.amount_paid - wizard.amount_delivered, 0.0) if limited else 0.0

    def action_confirm(self):
        self.ensure_one()
        lots = self.line_ids.filtered("selected").lot_id
        if not lots:
            raise UserError(_("Tick the generators that leave now."))
        order = self.order_id.sudo()
        value = self.amount_delivered + self.amount_selected
        if self.limited and order.currency_id.compare_amounts(value, self.amount_paid) > 0:
            raise UserError(order._x4u_over_paid_message(value))
        order._x4u_ship_generators(lots)
        return {"type": "ir.actions.act_window_close"}


class X4uJobOrderShipLine(models.TransientModel):
    _name = "x4u.job.order.ship.line"
    _description = "Deliver Generators: Generator"
    _order = "lot_id"

    wizard_id = fields.Many2one("x4u.job.order.ship", required=True, ondelete="cascade")
    lot_id = fields.Many2one("stock.lot", string="Generator Serial", required=True, readonly=True)
    product_id = fields.Many2one(related="lot_id.product_id", string="Model")
    generator = fields.Char(string="Generator", compute="_compute_generator")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    amount = fields.Monetary(string="Value", compute="_compute_generator", help="Its price on the sales order, with VAT.")
    selected = fields.Boolean(string="Deliver Now")

    @api.depends("lot_id")
    def _compute_generator(self):
        Production = self.env["mrp.production"].sudo()
        Ready = self.env["x4u.ready.order"].sudo()
        for line in self:
            production = Production.search([("lot_producing_id", "=", line.lot_id.id)], limit=1)
            ready = Ready.search([("lot_id", "=", line.lot_id.id)], limit=1)
            sale_line = production._x4u_sale_line() if production else ready.sale_line_id
            line.generator = production.name or ready.name or False
            line.amount = line.wizard_id.order_id.sudo()._x4u_unit_total(sale_line) if sale_line else 0.0
