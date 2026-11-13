from odoo import _, api, fields, models

from .mrp_production import PROFIT_DOMAIN

READY_STATES = [
    ("waiting", "Waiting Purchase"),
    ("in_stock", "In Stock"),
    ("delivered", "Delivered"),
    ("cancelled", "Cancelled"),
]


class X4uReadyOrder(models.Model):
    """Ready Job Order (spec v0.7 G1-G6): a generator bought complete from a supplier, not assembled.

    One per generator sold with Supply = Buy Ready. Its number (RG001) becomes the generator's serial
    at the receipt, it goes to stock as a finished good, then to the customer. It has its own
    analytic account like an assembled Job Order, so its margin shows the same way."""

    _name = "x4u.ready.order"
    _description = "Ready Job Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _check_company_auto = True

    name = fields.Char(string="Number", required=True, readonly=True, copy=False, default=lambda self: _("New"), index=True)
    sale_line_id = fields.Many2one("sale.order.line", string="Sales Line", readonly=True, index=True, ondelete="restrict")
    sale_order_id = fields.Many2one(related="sale_line_id.order_id", string="Sales Order", store=True, index=True)
    customer_id = fields.Many2one(
        related="sale_line_id.order_id.partner_id", string="Customer", store=True, index=True
    )
    product_id = fields.Many2one(related="sale_line_id.product_id", string="Generator", store=True, index=True)
    company_id = fields.Many2one(related="sale_line_id.company_id", store=True, index=True)
    state = fields.Selection(READY_STATES, default="waiting", required=True, readonly=True, tracking=True, index=True)
    lot_id = fields.Many2one("stock.lot", string="Serial No", readonly=True, copy=False)
    # Spec v0.8 N7: written at the receipt, from the supplier's papers; copied to the generator card.
    engine_serial = fields.Char(string="Engine Serial", readonly=True, copy=False, tracking=True)
    alternator_serial = fields.Char(string="Alternator Serial", readonly=True, copy=False, tracking=True)
    supplier_serial = fields.Char(string="Supplier Serial No", readonly=True, copy=False, tracking=True)
    generator_id = fields.Many2one("x4u.generator", string="Generator Card", compute="_compute_generator")
    analytic_account_id = fields.Many2one("account.analytic.account", string="Analytic Account", readonly=True, copy=False)
    currency_id = fields.Many2one(related="company_id.currency_id")
    margin = fields.Monetary(string="Margin", compute="_compute_margin")
    purchase_status = fields.Char(string="Purchase", compute="_compute_purchase")
    purchase_order_id = fields.Many2one("purchase.order", string="Purchase Order", compute="_compute_purchase")
    request_id = fields.Many2one("purchase.request", string="Material Request", compute="_compute_purchase")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("x4u.ready.order") or _("New")
        orders = super().create(vals_list)
        orders._x4u_analytic()
        return orders

    def _x4u_analytic(self):
        plan = self.env.ref("x4u_job_order.analytic_plan_job_orders", raise_if_not_found=False)
        if not plan:
            return
        Account = self.env["account.analytic.account"].sudo()
        for order in self.sudo().filtered(lambda o: not o.analytic_account_id):
            partner = order.customer_id.commercial_partner_id
            order.analytic_account_id = Account.create(
                {
                    "name": partner.name or order.product_id.display_name,
                    "code": order.name,
                    "plan_id": plan.id,
                    "company_id": order.company_id.id,
                    "partner_id": partner.id,
                }
            )

    def _compute_generator(self):
        for order in self:
            order.generator_id = order.lot_id.sudo().x4u_generator_ids[:1]

    def _compute_margin(self):
        accounts = self.analytic_account_id
        margins = {}
        if accounts:
            for account, amount in self.env["account.analytic.line"].sudo()._read_group(
                [("account_id", "in", accounts.ids), *PROFIT_DOMAIN], ["account_id"], ["amount:sum"]
            ):
                margins[account.id] = amount
        for order in self:
            order.margin = margins.get(order.analytic_account_id.id, 0.0)

    def _x4u_moves(self):
        """The customer delivery moves of the sales line: the purchase is chained to them."""
        return self.sale_line_id.sudo().move_ids.filtered(lambda move: move.state != "cancel")

    def _compute_purchase(self):
        for order in self:
            moves = order._x4u_moves()
            receipts = moves.move_orig_ids.filtered(lambda move: move.state != "cancel")
            po_lines = (
                self.env["purchase.order.line"].sudo().search([("move_dest_ids", "in", moves.ids)])
                | receipts.purchase_line_id
            ).filtered(lambda line: line.state != "cancel")
            requests = self.env["purchase.request.line"].sudo().search(
                [("move_dest_ids", "in", moves.ids), ("cancelled", "=", False)]
            ).request_id
            order.purchase_order_id = po_lines[:1].order_id
            order.request_id = requests[:1]
            if order.state in ("in_stock", "delivered"):
                status = _("Received")
            elif po_lines:
                po = po_lines[:1].order_id
                status = _("%(po)s · Ordered", po=po.name) if po.state in ("purchase", "done") else _("%(po)s · RFQ", po=po.name)
                if po_lines[:1].date_planned and po.state in ("purchase", "done"):
                    status += " · %s" % po_lines[:1].date_planned.strftime("%d/%m")
            elif requests:
                status = _("%(request)s · Requested", request=requests[:1].name)
            else:
                status = False
            order.purchase_status = status

    def _x4u_received(self, lots, picking):
        """At the receipt: the serial with the order's number, the card filled, the Accountant told."""
        for order in self.sudo():
            lot = lots.filtered(lambda l, o=order: l.name == o.name)[:1]
            if not lot or order.lot_id:
                continue
            order.write({"lot_id": lot.id, "state": "in_stock"})
            card = lot.x4u_generator_ids[:1]
            if card:
                sale = order.sale_order_id
                vals = {"sale_order_id": sale.id, "customer_id": sale.partner_id.commercial_partner_id.id}
                for source, target in (
                    ("engine_serial", "engine_serial"),
                    ("alternator_serial", "alternator_serial"),
                    ("supplier_serial", "x4u_supplier_serial"),
                ):
                    if order[source]:
                        vals[target] = order[source]
                card.write(vals)
            order.message_post(body=_("Received in %(picking)s: in stock as a finished generator.", picking=picking.name))
        sales = self.sale_order_id.sudo().filtered(lambda o: o.x4u_pay_before_delivery and not o.x4u_final_invoice_paid)
        for sale in sales:
            pending = self.sudo().search([("sale_order_id", "=", sale.id), ("state", "=", "waiting")])
            jobs = self.env["mrp.production"].sudo().search(
                [("x4u_sale_order_id", "=", sale.id), ("x4u_is_job_order", "=", True), ("x4u_job_state", "!=", "cancelled")]
            )
            if not pending and all(job.x4u_job_state in ("finished", "delivered") for job in jobs):
                sale._x4u_notify_accountant(
                    _("Generator ready: issue the tax invoice of %s and collect the balance before delivery", sale.name)
                )

    def action_open_purchase(self):
        self.ensure_one()
        if self.purchase_order_id:
            return {"type": "ir.actions.act_window", "res_model": "purchase.order", "res_id": self.purchase_order_id.id, "view_mode": "form"}
        if self.request_id:
            return {"type": "ir.actions.act_window", "res_model": "purchase.request", "res_id": self.request_id.id, "view_mode": "form"}
        return False

    def action_open_generator(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "x4u.generator", "res_id": self.generator_id.id, "view_mode": "form"}

    def action_open_profitability(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("x4u_job_order.action_x4u_job_profitability")
        action["domain"] = [("account_id", "=", self.analytic_account_id.id), *PROFIT_DOMAIN]
        action["display_name"] = _("Profitability of %s", self.name)
        return action
