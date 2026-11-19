from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# The parts of a generator shown one by one on the cost sheet (spec v0.14 H2); the others are summed.
PART_LABELS = {"engine": "Engine", "ckd": "CKD", "alternator": "Alternator", "body": "Canopy"}
ACCOUNTANT = "account.group_account_invoice"


class X4uJobOrder(models.Model):
    _inherit = "x4u.job.order"

    # Spec v0.14 H1: the overhead of this Job Order's generators, the general rate unless the
    # Accountant changes it for this order.
    overhead_percent = fields.Float(
        string="Overhead (%)",
        default=lambda self: self._x4u_default_overhead(),
        tracking=True,
        help="Added to what the parts of each generator cost when it is finished (consumables, power, labour, "
        "transport). The Accountant changes it for this Job Order; a generator finished afterwards takes it.",
    )
    can_edit_overhead = fields.Boolean(compute="_compute_can_edit_overhead")
    # H4: the order's figures for the Order Profitability list, kept up to date (H5).
    x4u_revenue = fields.Monetary(string="Revenue", readonly=True, copy=False, help="What the order is sold at, before VAT.")
    x4u_cost = fields.Monetary(string="Cost", readonly=True, copy=False, help="Generators, other goods and direct costs.")
    x4u_direct_cost = fields.Monetary(string="Direct Costs", readonly=True, copy=False)
    x4u_profit = fields.Monetary(string="Profit", readonly=True, copy=False)
    x4u_margin_percent = fields.Float(string="Margin (%)", readonly=True, copy=False, aggregator="avg")
    x4u_invoice_date = fields.Date(string="Invoiced On", readonly=True, copy=False, help="The date of the tax invoice.")
    x4u_profit_status = fields.Selection(
        [("estimated", "Estimated"), ("actual", "Actual")], string="Figures", readonly=True, copy=False,
        help="Actual once every generator is finished and the tax invoice is issued.",
    )
    x4u_cost_sheet = fields.Html(string="Cost Sheet", compute="_compute_x4u_cost_sheet", sanitize=False)

    @api.model
    def _x4u_default_overhead(self):
        return float(self.env["ir.config_parameter"].sudo().get_param("x4u_job_order.overhead_percent") or 0.0)

    @api.depends_context("uid")
    def _compute_can_edit_overhead(self):
        accountant = self.env.user.has_group(ACCOUNTANT)
        for job in self:
            job.can_edit_overhead = accountant and job.state not in ("finished", "delivered", "cancelled")

    def write(self, vals):
        if "overhead_percent" in vals and not self.env.su:
            if not self.env.user.has_group(ACCOUNTANT):
                raise UserError(_("The Accountant sets the overhead of a Job Order."))
            closed = self.filtered(lambda job: job.state in ("finished", "delivered", "cancelled"))
            if closed:
                raise UserError(_("%s: every generator is finished, its value is set.", ", ".join(closed.mapped("name"))))
        return super().write(vals)

    # ------------------------------------------------------------------
    # The cost sheet (H2, H3)
    # ------------------------------------------------------------------
    @api.model
    def _x4u_lot_cost(self, lot):
        """What a serial cost: its value in stock (purchase + landed costs), or what it left at."""
        lot = lot.sudo()
        if not lot:
            return 0.0
        if lot.avg_cost:
            return lot.avg_cost
        layer = self.env["stock.valuation.layer"].sudo().search(
            [("lot_id", "=", lot.id), ("quantity", "<", 0)], order="id desc", limit=1
        )
        if layer and layer.quantity:
            return layer.value / layer.quantity
        return lot.standard_price or lot.product_id.standard_price

    @api.model
    def _x4u_unit_price(self, line):
        """A unit of the sales line, before VAT."""
        return line.price_subtotal / line.product_uom_qty if line and line.product_uom_qty else 0.0

    def _x4u_generator_row(self, production):
        production = production.sudo()
        done = production.state == "done"
        parts, other = [], 0.0
        for move in production.move_raw_ids.filtered(lambda m: m.state != "cancel"):
            role = move.x4u_role
            if done and move.state == "done":
                cost = -sum(move.stock_valuation_layer_ids.mapped("value"))
                serials = move.move_line_ids.lot_id.mapped("name")
            else:
                lot = production.x4u_engine_lot_id if role in ("engine", "ckd") else (
                    production.x4u_body_lot_id if role == "body" else move.move_line_ids.lot_id[:1]
                )
                qty = move.product_uom._compute_quantity(move.product_uom_qty, move.product_id.uom_id)
                cost = self._x4u_lot_cost(lot) * qty if lot else move.product_id.standard_price * qty
                serials = lot.mapped("name")
            if role == "alternator":
                serials = production.x4u_alternator_id.mapped("name") or serials
            if role in PART_LABELS:
                parts.append(
                    {"label": PART_LABELS[role], "product": move.product_id.display_name, "serial": ", ".join(serials), "cost": cost}
                )
            else:
                other += cost
        materials = sum(part["cost"] for part in parts) + other
        if done:
            overhead = production.extra_cost * production.qty_produced
            rate = overhead / materials * 100 if materials else 0.0
        else:
            rate = self.overhead_percent
            overhead = materials * rate / 100
        line = production._x4u_sale_line()
        price = self._x4u_unit_price(line)
        cost = materials + overhead
        return {
            "name": production.name,
            "model": production.product_id.display_name,
            "serial": production.lot_producing_id.name or "",
            "status": "actual" if done else "estimated",
            "parts": parts,
            "other": other,
            "materials": materials,
            "rate": rate,
            "overhead": overhead,
            "cost": cost,
            "price": price,
            "profit": price - cost,
            "line": line,
        }

    def _x4u_ready_row(self, ready):
        ready = ready.sudo()
        line = ready.sale_line_id
        if ready.lot_id:
            cost, status = self._x4u_lot_cost(ready.lot_id), "actual"
        else:
            po_line = ready.purchase_order_id.order_line.filtered(lambda l: l.product_id == ready.product_id)[:1]
            cost = po_line.price_unit if po_line else ready.product_id.standard_price
            status = "estimated"
        price = self._x4u_unit_price(line)
        return {
            "name": ready.name,
            "model": ready.product_id.display_name,
            "serial": ready.lot_id.name or "",
            "status": status,
            "parts": [],
            "other": 0.0,
            "materials": cost,
            "rate": 0.0,
            "overhead": 0.0,
            "cost": cost,
            "price": price,
            "profit": price - cost,
            "line": line,
        }

    def _x4u_other_rows(self, generator_lines):
        """H3: the other lines of the order (spare parts, services), at their price and cost."""
        rows = []
        for line in self.sale_order_id.sudo().order_line:
            if line.display_type or line.is_downpayment or line in generator_lines or not line.product_id:
                continue
            cost = 0.0
            if line.product_id.is_storable:
                done = line.move_ids.filtered(lambda m: m.state == "done" and m.location_dest_id.usage == "customer")
                delivered = sum(done.mapped("product_qty"))
                cost = -sum(done.stock_valuation_layer_ids.mapped("value"))
                left = line.product_uom._compute_quantity(line.product_uom_qty, line.product_id.uom_id) - delivered
                cost += max(left, 0.0) * line.product_id.standard_price
            rows.append({"product": line.name, "qty": line.product_uom_qty, "price": line.price_subtotal, "cost": cost})
        return rows

    def _x4u_direct_rows(self):
        """H3: vendor bills and entries on the Job Order's analytic account (transport, crane,
        installation); not the cost of sales, which is in the generators above."""
        accounts = self.sudo()._x4u_accounts()
        if not accounts:
            return []
        stock_journals = self.env["product.category"].sudo().search([]).property_stock_journal
        lines = self.env["account.analytic.line"].sudo().search(
            [("account_id", "in", accounts.ids), ("amount", "<", 0), ("general_account_id.internal_group", "=", "expense")],
            order="date, id",
        )
        rows = []
        for line in lines:
            move = line.move_line_id.move_id
            if line.move_line_id.display_type == "cogs" or move.move_type in ("out_invoice", "out_refund"):
                continue
            if move and (move.journal_id in stock_journals or move.stock_move_id):
                continue
            rows.append(
                {
                    "date": line.date,
                    "document": move.name or line.name or "",
                    "partner": (line.partner_id or move.partner_id).display_name or "",
                    "account": line.general_account_id.display_name,
                    "cost": -line.amount,
                }
            )
        return rows

    def _x4u_cost_sheet_values(self):
        """The order's profitability: each generator by its serials, the other lines, the direct costs."""
        self.ensure_one()
        generators = [self._x4u_generator_row(p) for p in self.production_ids.filtered(lambda p: p.state != "cancel").sorted("name")]
        generators += [self._x4u_ready_row(r) for r in self.ready_order_ids.filtered(lambda r: r.state != "cancelled").sorted("name")]
        generator_lines = self.env["sale.order.line"].browse([row["line"].id for row in generators if row["line"]])
        others = self._x4u_other_rows(generator_lines)
        direct = self._x4u_direct_rows()
        revenue = sum(row["price"] for row in generators) + sum(row["price"] for row in others)
        generator_cost = sum(row["cost"] for row in generators)
        other_cost = sum(row["cost"] for row in others)
        direct_cost = sum(row["cost"] for row in direct)
        cost = generator_cost + other_cost + direct_cost
        invoices = self.sale_order_id.sudo()._x4u_final_invoices() if self.sale_order_id else self.env["account.move"]
        actual = bool(invoices) and all(row["status"] == "actual" for row in generators)
        return {
            "job": self,
            "currency": self.currency_id,
            "generators": generators,
            "others": others,
            "direct": direct,
            "revenue": revenue,
            "generator_cost": generator_cost,
            "other_cost": other_cost,
            "direct_cost": direct_cost,
            "cost": cost,
            "profit": revenue - cost,
            "margin": (revenue - cost) / revenue * 100 if revenue else 0.0,
            "invoice_date": min(invoices.mapped("invoice_date")) if invoices.filtered("invoice_date") else False,
            "status": "actual" if actual else "estimated",
        }

    @api.depends_context("uid")
    def _compute_x4u_cost_sheet(self):
        for job in self:
            if not self.env.user.has_group("account.group_account_readonly") and not self.env.user.has_group(ACCOUNTANT):
                job.x4u_cost_sheet = False
                continue
            job.x4u_cost_sheet = self.env["ir.qweb"]._render(
                "x4u_job_order.cost_sheet_table", {"sheet": job._x4u_cost_sheet_values()}
            )

    def _x4u_refresh_profitability(self):
        """H5: the figures of the Order Profitability list."""
        for job in self.sudo().filtered(lambda j: j.sale_order_id):
            sheet = job._x4u_cost_sheet_values()
            job.with_context(tracking_disable=True).write(
                {
                    "x4u_revenue": sheet["revenue"],
                    "x4u_cost": sheet["cost"],
                    "x4u_direct_cost": sheet["direct_cost"],
                    "x4u_profit": sheet["profit"],
                    "x4u_margin_percent": sheet["margin"],
                    "x4u_invoice_date": sheet["invoice_date"],
                    "x4u_profit_status": sheet["status"],
                }
            )

    @api.model
    def _cron_x4u_refresh_profitability(self):
        """Every night: the open Job Orders and those of the last 90 days."""
        since = fields.Datetime.now() - timedelta(days=90)
        self.search(["|", ("state", "not in", ("delivered", "cancelled")), ("write_date", ">=", since)])._x4u_refresh_profitability()

    def action_refresh_profitability(self):
        self._x4u_refresh_profitability()
        return True

    def action_print_cost_sheet(self):
        self.ensure_one()
        self._x4u_refresh_profitability()
        return self.env.ref("x4u_job_order.action_report_cost_sheet").report_action(self)
