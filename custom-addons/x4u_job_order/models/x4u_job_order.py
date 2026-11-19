from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .mrp_production import JOB_STATES, PROFIT_DOMAIN, STAGES
from .serial_search import serial_domain

# Spec v0.12 J5: the Job Order is where its slowest generator is.
PROGRESS = ("waiting_parts", "parts_ready", "material_delivered", "finished", "delivered")
READY_PROGRESS = {"waiting": "waiting_parts", "in_stock": "finished", "delivered": "delivered"}


class X4uJobOrder(models.Model):
    """The Job Order of a sales order (spec v0.12 J1): one for all its generators, any model,
    assembled or bought ready. Inside, each assembled generator is its own manufacturing order
    (MO020/1, MO020/2: its parts, serials and value) and each ready one its Ready Job Order (J2)."""

    _name = "x4u.job.order"
    _description = "Job Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _check_company_auto = True

    name = fields.Char(string="Job Order", required=True, readonly=True, copy=False, index="trigram")
    sale_order_id = fields.Many2one(
        "sale.order", string="Sales Order", readonly=True, index="btree_not_null", ondelete="restrict",
        check_company=True,
    )
    partner_id = fields.Many2one(related="sale_order_id.partner_id", string="Customer", store=True, index=True)
    company_id = fields.Many2one(
        "res.company", required=True, readonly=True, index=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    production_ids = fields.One2many("mrp.production", "x4u_job_id", string="Generators")
    ready_order_ids = fields.One2many("x4u.ready.order", "job_id", string="Ready Generators")
    proforma_names = fields.Char(
        string="PI", compute="_compute_proforma_names", store=True, index="trigram",
        help="The proforma invoice (PI) of the sales order.",
    )
    state = fields.Selection(
        JOB_STATES, string="Job Status", compute="_compute_progress", store=True, index=True, tracking=True,
        group_expand="_read_group_state",
    )
    generator_count = fields.Integer(string="Generators", compute="_compute_progress", store=True)
    finished_count = fields.Integer(string="Finished", compute="_compute_progress", store=True)
    delivered_count = fields.Integer(string="Delivered", compute="_compute_progress", store=True)
    progress = fields.Char(compute="_compute_progress", store=True)
    models_summary = fields.Char(string="Models", compute="_compute_progress", store=True)
    material_flag = fields.Selection(
        [("missing", "Missing Parts"), ("ready", "Materials Ready")],
        string="Materials", compute="_compute_progress", store=True, index=True,
        help="Red: a generator of this Job Order is short of a part. Green: every generator has its parts.",
    )
    delay_stage = fields.Selection(
        [(key, label) for key, label, _starts, _end in STAGES], string="Delay At",
        compute="_compute_progress", store=True, index=True,
    )
    delay_days = fields.Float(string="Delay (days)", compute="_compute_progress", store=True)
    date_deadline = fields.Datetime(string="Deadline", compute="_compute_progress", store=True)
    can_deliver = fields.Boolean(compute="_compute_progress", store=True)
    can_finish = fields.Boolean(compute="_compute_progress", store=True)
    # Spec v0.13 L2: a finished generator (or a ready one received) waits for its Delivery Note.
    can_ship = fields.Boolean(compute="_compute_progress", store=True)
    # Spec v0.12 J7: one analytic account for the order's Job Order.
    analytic_account_id = fields.Many2one(
        "account.analytic.account", string="Analytic Account", readonly=True, copy=False, index="btree_not_null"
    )
    margin = fields.Monetary(string="Margin", compute="_compute_margin")
    serial_search = fields.Char(
        string="Serial", compute="_compute_serial_search", search="_search_serial",
        help="The serial of a generator of the Job Order, or of its engine, CKD, canopy or alternator.",
    )
    event_ids = fields.Many2many("x4u.job.order.event", string="Timeline", compute="_compute_lines")
    move_raw_ids = fields.Many2many("stock.move", string="Parts", compute="_compute_lines")
    request_count = fields.Integer(string="Material Requests", compute="_compute_lines")
    card_count = fields.Integer(string="Generator Cards", compute="_compute_lines")

    _sql_constraints = [
        ("x4u_sale_order_unique", "unique(sale_order_id)", "A sales order has one Job Order."),
    ]

    @api.model
    def _read_group_state(self, values, domain):
        return [key for key, _label in JOB_STATES if key != "cancelled"]

    @api.model
    def _x4u_for_order(self, order, picking_type=None):
        """The Job Order of the sales order, opened with the next Job Order number (J1)."""
        job = self.sudo().search([("sale_order_id", "=", order.id)], limit=1)
        if job:
            return job
        picking_type = picking_type or order.warehouse_id.manu_type_id
        return self.sudo().create(
            {"name": self._x4u_next_name(picking_type), "sale_order_id": order.id, "company_id": order.company_id.id}
        )

    @api.model
    def _x4u_next_name(self, picking_type):
        sequence = picking_type.sudo().sequence_id
        return (sequence.next_by_id() if sequence else None) or self.env["ir.sequence"].next_by_code("mrp.production") or _("New")

    @api.depends("sale_order_id.x4u_proforma_ids.name", "sale_order_id.x4u_proforma_ids.state")
    def _compute_proforma_names(self):
        for job in self:
            proformas = job.sale_order_id.sudo().x4u_proforma_ids.filtered(lambda pi: pi.state != "cancel")
            job.proforma_names = ", ".join(proformas.sorted("id").mapped("name")) or False

    @api.depends(
        "production_ids.x4u_job_state",
        "production_ids.x4u_material_flag",
        "production_ids.x4u_delay_stage",
        "production_ids.x4u_delay_days",
        "production_ids.date_deadline",
        "production_ids.product_id",
        "ready_order_ids.state",
        "ready_order_ids.product_id",
    )
    def _compute_progress(self):
        for job in self:
            productions = job.production_ids.filtered(lambda p: p.x4u_job_state and p.x4u_job_state != "cancelled")
            ready = job.ready_order_ids.filtered(lambda o: o.state != "cancelled")
            states = productions.mapped("x4u_job_state") + [READY_PROGRESS[state] for state in ready.mapped("state")]
            count = len(states)
            finished = sum(1 for state in states if state in ("finished", "delivered"))
            delivered = states.count("delivered")
            if states:
                job.state = min(states, key=PROGRESS.index)
            else:
                job.state = "cancelled" if job.production_ids or job.ready_order_ids else False
            job.generator_count = count
            job.finished_count = finished
            job.delivered_count = delivered
            job.progress = _("Finished %(finished)s / %(count)s · Delivered %(delivered)s / %(count)s",
                             finished=finished, delivered=delivered, count=count) if count else False
            products = {}
            for product in productions.product_id | ready.product_id:
                products[product] = len(productions.filtered(lambda p, pr=product: p.product_id == pr)) + len(
                    ready.filtered(lambda o, pr=product: o.product_id == pr)
                )
            job.models_summary = ", ".join("%s × %s" % (qty, product.display_name) for product, qty in products.items()) or False
            flags = productions.mapped("x4u_material_flag")
            job.material_flag = "missing" if "missing" in flags else ("ready" if "ready" in flags else False)
            late = productions.filtered("x4u_delay_stage").sorted("x4u_delay_days", reverse=True)[:1]
            job.delay_stage = late.x4u_delay_stage
            job.delay_days = late.x4u_delay_days
            deadlines = [date for date in productions.mapped("date_deadline") if date]
            job.date_deadline = min(deadlines) if deadlines else False
            job.can_deliver = any(state in ("waiting_parts", "parts_ready") for state in productions.mapped("x4u_job_state"))
            job.can_finish = "material_delivered" in productions.mapped("x4u_job_state")
            job.can_ship = bool(job.sale_order_id) and (
                "finished" in productions.mapped("x4u_job_state") or "in_stock" in ready.mapped("state")
            )

    def _compute_lines(self):
        for job in self:
            productions = job.production_ids.sudo()
            job.event_ids = productions.x4u_event_ids
            job.move_raw_ids = productions.move_raw_ids.filtered(lambda m: m.state != "cancel")
            job.request_count = len(productions._x4u_purchase_requests())
            job.card_count = len(productions.lot_producing_id.x4u_generator_ids | job.ready_order_ids.lot_id.x4u_generator_ids)

    def _compute_serial_search(self):
        self.serial_search = False

    def _search_serial(self, operator, value):
        return serial_domain(self._x4u_ids_by_serial, operator, value)

    @api.model
    def _x4u_ids_by_serial(self, operator, value):
        Production = self.env["mrp.production"]
        Ready = self.env["x4u.ready.order"]
        productions = Production.sudo().browse(Production._x4u_ids_by_serial(operator, value))
        ready = Ready.sudo().browse(Ready._x4u_ids_by_serial(operator, value))
        return (productions.x4u_job_id | ready.job_id).ids

    # ------------------------------------------------------------------
    # Profitability (J7)
    # ------------------------------------------------------------------
    def _x4u_analytic(self):
        """The Job Order's analytic account (code = its number, name = the customer)."""
        plan = self.env.ref("x4u_job_order.analytic_plan_job_orders", raise_if_not_found=False)
        if not plan:
            return self.env["account.analytic.account"]
        self.ensure_one()
        job = self.sudo()
        partner = job.partner_id.commercial_partner_id
        account = job.analytic_account_id
        if not account:
            account = self.env["account.analytic.account"].sudo().create(
                {
                    "name": partner.name or job.name,
                    "code": job.name,
                    "plan_id": plan.id,
                    "company_id": job.company_id.id,
                    "partner_id": partner.id,
                }
            )
            job.analytic_account_id = account
        return account

    def _x4u_accounts(self):
        """Its account, and those of generators opened before v0.12 (one per generator)."""
        return (
            self.analytic_account_id
            | self.production_ids.x4u_analytic_account_id
            | self.ready_order_ids.analytic_account_id
        )

    def _compute_margin(self):
        for job in self:
            accounts = job.sudo()._x4u_accounts()
            amount = 0.0
            if accounts:
                groups = self.env["account.analytic.line"].sudo()._read_group(
                    [("account_id", "in", accounts.ids), *PROFIT_DOMAIN], [], ["amount:sum"]
                )
                amount = groups[0][0] if groups else 0.0
            job.margin = amount or 0.0

    # ------------------------------------------------------------------
    # Buttons (J4)
    # ------------------------------------------------------------------
    def action_deliver_materials(self):
        """Storekeeper: Deliver Materials of every generator still waiting, in one screen (D1),
        filled with the serials chosen on the Serial tab."""
        self.ensure_one()
        productions = self.production_ids._x4u_open_to_deliver()
        if not productions:
            raise UserError(_("%s has no generator waiting for its parts.", self.name))
        return self.env["x4u.job.order.deliver.all"]._x4u_action(productions)

    def action_finish(self):
        """Operation Manager: Finish the generators whose parts are delivered, a line each (D2)."""
        self.ensure_one()
        productions = self.production_ids.filtered(lambda p: p.x4u_job_state == "material_delivered")
        if not productions:
            raise UserError(_("%s has no generator with all its materials delivered.", self.name))
        return self.env["x4u.job.order.finish.all"]._x4u_action(productions)

    def action_ship(self):
        """Storekeeper: Deliver Generators, the ones that leave now (L2)."""
        self.ensure_one()
        return self.env["x4u.job.order.ship"]._x4u_action(self)

    def action_open_sale(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "sale.order", "res_id": self.sale_order_id.id, "view_mode": "form"}

    def action_open_requests(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("purchase_request.purchase_request_form_action")
        action["domain"] = [("id", "in", self.production_ids.sudo()._x4u_purchase_requests().ids)]
        action["context"] = {"create": False}
        return action

    def action_open_cards(self):
        self.ensure_one()
        cards = self.production_ids.sudo().lot_producing_id.x4u_generator_ids | self.ready_order_ids.sudo().lot_id.x4u_generator_ids
        return {
            "type": "ir.actions.act_window",
            "name": _("Generator Cards"),
            "res_model": "x4u.generator",
            "view_mode": "list,form",
            "domain": [("id", "in", cards.ids)],
            "context": {"create": False},
        }

    def action_open_productions(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("x4u_job_order.action_x4u_job_order")
        action["domain"] = [("x4u_job_id", "=", self.id)]
        action["context"] = {"create": False}
        return action

    def action_open_profitability(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("x4u_job_order.action_x4u_job_profitability")
        action["domain"] = [("account_id", "in", self.sudo()._x4u_accounts().ids), *PROFIT_DOMAIN]
        action["display_name"] = _("Profitability of %s", self.name)
        return action
