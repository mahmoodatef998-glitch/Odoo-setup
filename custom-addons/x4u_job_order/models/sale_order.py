from odoo import _, api, fields, models
from odoo.exceptions import UserError

SUPPLY = [("assemble", "Assembly"), ("ready", "Ready Product")]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    x4u_ready_order_ids = fields.One2many("x4u.ready.order", "sale_order_id", string="Ready Job Orders")
    x4u_ready_order_count = fields.Integer(compute="_compute_x4u_ready_order_count")

    def _compute_x4u_ready_order_count(self):
        for order in self:
            order.x4u_ready_order_count = len(order.x4u_ready_order_ids)

    def _x4u_send_problems(self):
        """x4u_sale spec v0.7 O1: every generator says Assembly or Ready Product, nobody opens an
        assembly by mistake."""
        problems = super()._x4u_send_problems()
        missing = self.order_line.filtered(lambda line: line.x4u_is_generator and not line.x4u_supply)
        if missing:
            problems.append(
                _("Supply (Assembly or Ready Product) for %s", ", ".join(missing.product_id.mapped("display_name")))
            )
        return problems

    def action_confirm(self):
        # Spec v0.7 G1: a generator bought ready is bought (one request for the complete generator),
        # not assembled from 3 parts.
        # The Accountant confirms (x4u_sale v0.7 O5) without Sales or Manufacturing rights: x4u_sale
        # checks him first, the routes and the Job Orders are set up with full rights.
        ready_lines = self.order_line.filtered(lambda line: line.x4u_supply == "ready" and line.x4u_is_generator)
        res = super(SaleOrder, self.with_context(x4u_ready_lines=ready_lines.ids)).action_confirm()
        for order in self.sudo():
            productions = order.mrp_production_ids
            productions._x4u_log("order_opened", document=order, date=order.date_order)
            # Odoo links the sale to the Job Order only after confirming it: fill the card now.
            productions._x4u_fill_generator_card()
            # ...and the customer on the Job Order's analytic account (spec v0.5 A1).
            productions._x4u_job_analytic()
        if ready_lines:
            ready_lines.sudo()._x4u_open_ready_orders()
        return res

    def _action_confirm(self):
        # Spec v0.7 G1: a generator bought ready is bought (one request for the complete generator),
        # not assembled from 3 parts. Here, after x4u_sale's checks, before the procurements.
        ready_lines = self.env["sale.order.line"].browse(self.env.context.get("x4u_ready_lines") or [])
        if ready_lines:
            buy = self.env.ref("purchase_stock.route_warehouse0_buy")
            ready_lines.sudo().write({"route_id": buy.id})
            templates = ready_lines.product_id.product_tmpl_id.sudo().filtered(lambda t: not t.purchase_request)
            templates.write({"purchase_request": True})
        return super()._action_confirm()

    def _action_cancel(self):
        res = super()._action_cancel()
        self.sudo().x4u_ready_order_ids.filtered(lambda o: o.state == "waiting").write({"state": "cancelled"})
        return res

    def action_x4u_open_ready_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("x4u_job_order.action_x4u_ready_order")
        action["domain"] = [("sale_order_id", "=", self.id)]
        return action


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    x4u_is_generator = fields.Boolean(related="product_id.x4u_is_generator", string="Is Generator")
    # x4u_sale spec v0.7 O1: no default, the Salesperson chooses before sending to the Accountant.
    x4u_supply = fields.Selection(
        SUPPLY, string="Supply",
        help="Assembly: a Job Order with its parts (engine, alternator, body). "
        "Ready Product: the complete generator is bought from a supplier and goes to stock as a finished good.",
    )

    @api.constrains("x4u_supply", "product_id")
    def _check_x4u_supply(self):
        for line in self:
            if line.x4u_supply == "ready" and line.product_id and not line.x4u_is_generator:
                raise UserError(_("Ready Product is for generators only (%s).", line.product_id.display_name))

    def _x4u_open_ready_orders(self):
        """One Ready Job Order per generator on the line, its material request approved and
        Purchasing told, like the parts of an assembled Job Order."""
        Ready = self.env["x4u.ready.order"].sudo()
        orders = Ready
        for line in self.sudo():
            count = int(line.product_uom._compute_quantity(line.product_uom_qty, line.product_id.uom_id))
            existing = Ready.search_count([("sale_line_id", "=", line.id)])
            orders |= Ready.create([{"sale_line_id": line.id} for _i in range(max(count - existing, 0))])
        requests = self.env["purchase.request.line"].sudo().search(
            [("move_dest_ids", "in", self.move_ids.ids), ("cancelled", "=", False)]
        ).request_id
        requests.filtered(lambda request: request.state in ("draft", "to_approve")).button_approved()
        user_id = int(self.env["ir.config_parameter"].sudo().get_param("x4u_job_order.purchase_user_id") or 0)
        for order in orders:
            if user_id:
                order.activity_schedule(
                    "mail.mail_activity_data_todo", user_id=user_id,
                    summary=_("Order the ready generator for %s", order.name),
                )
            order.message_post(
                body=_("Opened from %(sale)s: bought ready, %(requests)s.",
                       sale=order.sale_order_id.name, requests=", ".join(requests.mapped("name")) or "-")
            )
        plan = self.env.ref("x4u_job_order.analytic_plan_job_orders", raise_if_not_found=False)
        if plan:
            self._x4u_set_job_distribution(plan)
        return orders

    def _x4u_set_job_distribution(self, plan, backfill=False):
        """The line's analytic = its Job Orders (assembled or ready), shared equally (2 generators
        on one line: 50/50). A distribution someone chose by hand (another plan) stays. With
        `backfill`, the lines already invoiced and their cost of sales get it too (spec v0.5)."""
        Production = self.env["mrp.production"].sudo()
        Ready = self.env["x4u.ready.order"].sudo()
        for line in self.sudo():
            productions = Production.search(
                ["|", ("sale_line_id", "=", line.id), ("x4u_sale_order_id", "=", line.order_id.id),
                 ("x4u_is_job_order", "=", True), ("state", "!=", "cancel")]
            )
            accounts = productions.filtered(lambda p, line=line: p._x4u_sale_line() == line).x4u_analytic_account_id
            accounts |= Ready.search([("sale_line_id", "=", line.id), ("state", "!=", "cancelled")]).analytic_account_id
            if not accounts:
                continue
            current = line.analytic_distribution or {}
            current_ids = {int(account_id) for key in current for account_id in key.split(",")}
            if current_ids and self.env["account.analytic.account"].sudo().browse(current_ids).plan_id != plan:
                continue
            share = 100.0 / len(accounts)
            distribution = {str(account.id): share for account in accounts}
            if distribution != current:
                # Confirmed orders lock themselves (Lock Confirmed Sales); the analytic is the
                # Job Order's bookkeeping, not a change to what the customer ordered.
                order = line.order_id
                locked = order.locked
                if locked:
                    order.locked = False
                line.analytic_distribution = distribution
                if locked:
                    order.locked = True
            if backfill:
                invoice_lines = line.invoice_lines.filtered(lambda inv_line: inv_line.parent_state != "cancel")
                cogs_lines = invoice_lines.move_id.line_ids.filtered(
                    lambda aml: aml.display_type == "cogs" and aml.product_id == line.product_id
                )
                (invoice_lines | cogs_lines).filtered(
                    lambda aml: aml.analytic_distribution != distribution
                ).analytic_distribution = distribution
