from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount

SUPPLY = [("assemble", "Assembly"), ("ready", "Ready Product")]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    x4u_ready_order_ids = fields.One2many("x4u.ready.order", "sale_order_id", string="Ready Job Orders")
    x4u_ready_order_count = fields.Integer(compute="_compute_x4u_ready_order_count")
    # Spec v0.12 J1: the order's one Job Order.
    x4u_job_ids = fields.One2many("x4u.job.order", "sale_order_id", string="Job Order")
    # x4u_generator_datasheet §9 (QT 1112): a quotation of options, each generator one option with its
    # own total; the customer picks one, the Salesperson keeps it (Choose) before the PI.
    x4u_quote_options = fields.Boolean(
        string="Quote as Options",
        help="Each generator is an option (A, B, C...) with its own total, as in QT 1112. "
        "Choose the one the customer ordered before the PI.",
    )
    x4u_requirement = fields.Html(
        string="Requirement",
        help="Printed in the yellow box at the top of the quotation: what the customer asked for and the options offered.",
    )
    x4u_attention = fields.Char(string="Attention", help="Printed under the customer, e.g. Purchasing Department.")
    x4u_delivery_note = fields.Text(
        string="Delivery",
        help="Printed in the Delivery box, e.g. Ex-Works SAIF Zone, freight quoted after approval, lead time.",
    )

    def _compute_x4u_ready_order_count(self):
        for order in self:
            order.x4u_ready_order_count = len(order.x4u_ready_order_ids)

    def _x4u_option_lines(self):
        """The options of the quotation (its generator lines), in their order."""
        self.ensure_one()
        return self.order_line.filtered(lambda line: line.x4u_is_generator and not line.display_type).sorted("sequence")

    def _x4u_common_lines(self):
        """The other priced lines: added to every option."""
        self.ensure_one()
        return self.order_line.filtered(lambda line: not line.display_type and not line.x4u_is_generator)

    def _x4u_validity_days(self):
        self.ensure_one()
        if not self.validity_date or not self.date_order:
            return 0
        return (self.validity_date - self.date_order.date()).days

    def _x4u_options_problem(self):
        self.ensure_one()
        if self.x4u_quote_options and len(self._x4u_option_lines()) > 1:
            return _("%s is a quotation of options: press Choose on the option the customer ordered.", self.name)
        return ""

    def _x4u_send_problems(self, pi_comes_with_it=False):
        """x4u_sale spec v0.7 O1: every generator says Assembly or Ready Product, nobody opens an
        assembly by mistake."""
        problems = super()._x4u_send_problems(pi_comes_with_it=pi_comes_with_it)
        missing = self.order_line.filtered(lambda line: line.x4u_is_generator and not line.x4u_supply)
        if missing:
            problems.append(
                _("Supply (Assembly or Ready Product) for %s", ", ".join(missing.product_id.mapped("display_name")))
            )
        for order in self:
            if order._x4u_options_problem():
                problems.append(order._x4u_options_problem())
        return problems

    @api.model
    def _x4u_internal_line_fields(self):
        # x4u_sale spec v0.8 Q4: the Supply is not on the PI, it can still be chosen after it.
        return super()._x4u_internal_line_fields() | {"x4u_supply"}

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
            # The user, 2026-11-26: a model Built from CKD takes its CKD by itself (Use CKD); the
            # material request then asks for the CKD, not the engine and the alternator.
            for production in productions.filtered(
                lambda p: p.product_id.product_tmpl_id.x4u_built_from_ckd and p.product_id.x4u_ckd_product_id
                and not p.x4u_uses_ckd and p.x4u_can_switch_parts
            ):
                production._x4u_switch_parts(production.product_id.x4u_ckd_product_id)
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

    # ------------------------------------------------------------------
    # Delivery within what was paid, and the tax invoice that takes the rest (spec v0.13 L1-L4)
    # ------------------------------------------------------------------
    def _x4u_delivery_within_paid(self):
        """L1: paid before delivery and no tax invoice yet: the goods delivered stay within the payments."""
        self.ensure_one()
        return bool(self.x4u_pay_before_delivery and not self._x4u_final_invoices())

    @api.model
    def _x4u_unit_total(self, line):
        """A unit of the line, with VAT, in the order's currency."""
        if not line or not line.product_uom_qty:
            return 0.0
        return line.price_total / line.product_uom_qty

    def _x4u_delivered_value(self):
        self.ensure_one()
        return sum(
            self._x4u_unit_total(line) * line.qty_delivered
            for line in self.order_line
            if not line.display_type and line.product_id.type == "consu"
        )

    def _x4u_over_paid_message(self, value):
        self.ensure_one()
        return _(
            "%(order)s is paid before delivery: %(paid)s paid, the goods delivered would be worth %(value)s. "
            "Record the next payment, or issue the tax invoice.",
            order=self.name,
            paid=format_amount(self.env, self._x4u_amount_received(), self.currency_id),
            value=format_amount(self.env, value, self.currency_id),
        )

    def _x4u_generator_lots_in_stock(self):
        """The finished (or received ready) generators of the order still in the warehouse."""
        self.ensure_one()
        jobs = self.sudo().x4u_job_ids
        lots = jobs.production_ids.filtered(lambda p: p.state == "done").lot_producing_id
        lots |= jobs.ready_order_ids.filtered(lambda o: o.state == "in_stock").lot_id
        if not lots:
            return lots
        quants = self.env["stock.quant"].sudo().search(
            [("lot_id", "in", lots.ids), ("location_id", "child_of", self.warehouse_id.lot_stock_id.id), ("quantity", ">", 0)]
        )
        return quants.lot_id

    def _x4u_generators_waiting(self):
        """L3: the generators of the order not finished (or not received) yet."""
        self.ensure_one()
        jobs = self.sudo().x4u_job_ids
        productions = jobs.production_ids.filtered(lambda p: p.x4u_job_state not in ("finished", "delivered", "cancelled"))
        ready = jobs.ready_order_ids.filtered(lambda o: o.state == "waiting")
        return productions.mapped("name") + ready.mapped("name")

    def _x4u_ship_generators(self, lots, from_invoice=False):
        """L2 / L4: these generators leave now on the order's delivery, by their serials; what else is
        on it (other generators, spare parts) waits on a backorder."""
        self.ensure_one()
        Quant = self.env["stock.quant"].sudo()
        remaining = lots
        for picking in self.sudo().picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing" and p.state not in ("done", "cancel") and p.location_dest_id.usage == "customer"
        ):
            moves = picking.move_ids.filtered(lambda m: m.product_id.x4u_is_generator and m.state not in ("done", "cancel"))
            wanted = remaining.filtered(lambda lot: lot.product_id in moves.product_id)
            if not wanted:
                continue
            picking.move_ids.filtered(lambda m: m.state not in ("done", "cancel")).picked = False
            for move in moves:
                take = remaining.filtered(lambda lot, p=move.product_id: lot.product_id == p)[: int(move.product_uom_qty)]
                move.move_line_ids.unlink()
                commands = []
                for lot in take:
                    quant = Quant._gather(move.product_id, move.location_id, lot_id=lot, strict=False).filtered(
                        lambda q: q.quantity > 0
                    )[:1]
                    commands.append(Command.create(move._prepare_move_line_vals(quantity=1, reserved_quant=quant)))
                if commands:
                    move.move_line_ids = commands
                    move.picked = True
                remaining -= take
            picking.with_context(skip_backorder=True, x4u_invoice_delivery=from_invoice).button_validate()
        return lots - remaining

    def action_x4u_create_proforma(self):
        """x4u_generator_datasheet §5: a generator without a price (Stamford, or a model the 2026
        price list does not have) is "price on request": the Salesperson types its price before the PI."""
        for order in self:
            if order._x4u_options_problem():
                raise UserError(order._x4u_options_problem())
            unpriced = order.order_line.filtered(
                lambda line: line.x4u_is_generator and not line.display_type and order.currency_id.is_zero(line.price_unit)
            )
            if unpriced:
                raise UserError(
                    _(
                        "Type the price of %s first: it is price on request (not in the 2026 price list).",
                        ", ".join(unpriced.mapped("product_id.display_name")),
                    )
                )
        return super().action_x4u_create_proforma()

    def action_x4u_create_tax_invoice(self):
        """L3: the tax invoice has every generator, so it comes when they are all ready."""
        for order in self:
            waiting = order._x4u_generators_waiting()
            if waiting:
                raise UserError(
                    _(
                        "%(order)s: the tax invoice takes every generator out of stock, and these are not ready yet: %(names)s.",
                        order=order.name,
                        names=", ".join(waiting),
                    )
                )
        return super().action_x4u_create_tax_invoice()

    def action_x4u_open_job(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "x4u.job.order", "res_id": self.x4u_job_ids[:1].id, "view_mode": "form"}

    def action_x4u_open_ready_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("x4u_job_order.action_x4u_ready_order")
        action["domain"] = [("sale_order_id", "=", self.id)]
        return action


class X4uSaleProforma(models.Model):
    _inherit = "x4u.sale.proforma"

    # The Job Order the PI's order opened (spec v0.12 J1), to open it from the PI.
    x4u_job_id = fields.Many2one("x4u.job.order", string="Job Order", compute="_compute_x4u_job_id")

    def _compute_x4u_job_id(self):
        for proforma in self:
            proforma.x4u_job_id = proforma.order_id.sudo().x4u_job_ids[:1]

    def action_x4u_open_job(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "x4u.job.order", "res_id": self.x4u_job_id.id, "view_mode": "form"}


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    x4u_is_generator = fields.Boolean(related="product_id.x4u_is_generator", string="Is Generator")
    # x4u_sale spec v0.7 O1: no default, the Salesperson chooses before sending to the Accountant.
    x4u_supply = fields.Selection(
        SUPPLY, string="Supply",
        help="Assembly: a Job Order with its parts (engine, alternator, body). "
        "Ready Product: the complete generator is bought from a supplier and goes to stock as a finished good.",
    )

    # x4u_generator_datasheet §5 (the user, 2026-11-24): extras on the generator line, like QT 1112 -
    # their text goes into the description, their price into the unit price. The price stays editable.
    x4u_extras = fields.Text(
        string="Extras",
        help="Added to this line (e.g. water jacket heater, anti-condensation heater, MCCB): printed in the description.",
    )
    x4u_extras_price = fields.Monetary(
        string="Extras Price", currency_field="currency_id",
        help="Added to the unit price. The unit price can still be changed by hand.",
    )

    # QT 1112: the option's badge and heading (e.g. "Cummins with Leroy-Somer alternator").
    x4u_option_tag = fields.Selection(
        [("recommended", "Recommended"), ("alternative", "Alternative")], string="Option",
        help="On a quotation of options: printed as a badge on the option.",
    )
    x4u_option_title = fields.Char(
        string="Option Title", help="The heading of the option on the quotation; empty: the engine brand and the alternator.",
    )

    def _x4u_option_letter(self):
        self.ensure_one()
        options = self.order_id._x4u_option_lines()
        return chr(ord("A") + options.ids.index(self.id)) if self.id in options.ids and len(options) <= 26 else ""

    def _x4u_option_heading(self):
        self.ensure_one()
        if self.x4u_option_title:
            return self.x4u_option_title
        brand = self.product_id.x4u_engine_brand_id.name or ""
        choice = self.product_id._x4u_alternator_choice() if self.product_id else ""
        heading = "%s with %s alternator" % (brand, "4U Power" if choice in ("4U", "AQT") else choice) if choice else brand
        if self.x4u_option_tag == "recommended":
            heading += " (4U recommendation)"
        elif self.x4u_option_tag == "alternative":
            heading += " (alternative)"
        return heading

    def _x4u_print_title_body(self):
        """(title, [description lines]) for the quotation: a generator as "4U-C300 — <model name>"."""
        self.ensure_one()
        lines = (self.name or "").split("\n")
        if self.x4u_is_generator and self.product_id.default_code:
            return "%s — %s" % (self.product_id.default_code, self.product_id.product_tmpl_id.name), lines[1:]
        return lines[0], lines[1:]

    def _x4u_option_total(self, field):
        """An option's subtotal / tax / total, the common lines added (each option is a separate total)."""
        self.ensure_one()
        return self[field] + sum(self.order_id._x4u_common_lines().mapped(field))

    def action_x4u_choose_option(self):
        """The customer chose this option: the other options leave the quotation."""
        self.ensure_one()
        order = self.order_id
        if order.state not in ("draft", "sent"):
            raise UserError(_("Only a quotation's options can be chosen."))
        others = order._x4u_option_lines() - self
        order.message_post(body=_("Option chosen: %(option)s. Removed: %(others)s.",
                                  option=self.product_id.display_name,
                                  others=", ".join(others.mapped("product_id.display_name")) or "-"))
        others.unlink()
        order.x4u_quote_options = False
        self.x4u_option_tag = False
        return True

    def _reset_price_unit(self):
        """The pricelist price plus the extras (the line keeps following the pricelist)."""
        res = super()._reset_price_unit()
        if self.x4u_extras_price:
            self.price_unit += self.x4u_extras_price
            self.technical_price_unit = self.price_unit
        return res

    # The user, 2026-11-26 (fewer steps): a generator is assembled unless the Salesperson picks
    # Ready Product (before, Supply had to be chosen on every line).
    @api.onchange("product_id")
    def _onchange_x4u_supply_default(self):
        if self.x4u_is_generator and not self.x4u_supply:
            self.x4u_supply = "assemble"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("x4u_supply") and vals.get("product_id") and not vals.get("display_type"):
                if self.env["product.product"].browse(vals["product_id"]).x4u_is_generator:
                    vals["x4u_supply"] = "assemble"
        return super().create(vals_list)

    @api.onchange("x4u_extras_price")
    def _onchange_x4u_extras_price(self):
        for line in self:
            change = line.x4u_extras_price - (line._origin.x4u_extras_price or 0.0)
            if change:
                manual = line.currency_id.compare_amounts(line.technical_price_unit, line.price_unit)
                line.price_unit += change
                if not manual:
                    line.technical_price_unit = line.price_unit

    @api.onchange("x4u_extras")
    def _onchange_x4u_extras(self):
        for line in self:
            name = line.name or ""
            old = (line._origin.x4u_extras or "").strip()
            if old and name.endswith(old):
                name = name[: -len(old)].rstrip("\n")
            new = (line.x4u_extras or "").strip()
            line.name = "%s\n%s" % (name, new) if new else name

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
            job = self.env["x4u.job.order"]._x4u_for_order(line.order_id)
            orders |= Ready.create([{"sale_line_id": line.id, "job_id": job.id} for _i in range(max(count - existing, 0))])
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
