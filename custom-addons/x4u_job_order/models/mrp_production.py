from odoo import _, api, fields, models

from .x4u_job_order_event import SINGLE_EVENTS

JOB_STATES = [
    ("waiting_parts", "Waiting Parts"),
    ("parts_ready", "Parts Ready"),
    ("material_delivered", "Material Delivered"),
    ("assembled", "Assembled & Tested"),
    ("finished", "Finished"),
    ("cancelled", "Cancelled"),
]

# Stage: (key, label, start events (latest wins), end event) — spec §7.2.
STAGES = [
    ("purchasing", "Purchasing", ("material_request",), "rfq_created"),
    ("approval", "Approval", ("rfq_created",), "po_approved"),
    ("supplier", "Supplier delivery", ("po_approved", "po_sent"), "parts_ready"),
    ("warehouse", "Warehouse issue", ("parts_ready",), "material_delivered"),
    ("assembly", "Assembly & test", ("material_delivered",), "assembled"),
    ("qc", "QC", ("assembled",), "qc_passed"),
    ("dispatch", "Dispatch", ("qc_passed",), "delivered"),
]
STAGE_KEYS = [stage[0] for stage in STAGES]
PART_ROLES = ("engine", "alternator", "body")


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    x4u_is_job_order = fields.Boolean(
        string="Is Job Order", compute="_compute_x4u_is_job_order", store=True, index=True
    )
    x4u_job_state = fields.Selection(
        JOB_STATES,
        string="Job Status",
        copy=False,
        index=True,
        tracking=True,
        readonly=True,
        group_expand="_read_group_x4u_job_state",
    )
    x4u_event_ids = fields.One2many("x4u.job.order.event", "production_id", string="Timeline")
    x4u_sale_order_id = fields.Many2one(
        "sale.order", string="Sales Order", compute="_compute_x4u_sale_order", store=True, index=True
    )
    x4u_customer_id = fields.Many2one(
        related="x4u_sale_order_id.partner_id", string="Customer", store=True, index=True
    )
    x4u_generator_id = fields.Many2one(related="lot_producing_id.x4u_generator_id", string="Generator Card")
    x4u_request_count = fields.Integer(compute="_compute_x4u_documents", string="Material Requests")
    x4u_engine_status = fields.Char(compute="_compute_x4u_parts", string="Engine")
    x4u_alternator_status = fields.Char(compute="_compute_x4u_parts", string="Alternator")
    x4u_body_status = fields.Char(compute="_compute_x4u_parts", string="Body")
    x4u_days_purchasing = fields.Float(compute="_compute_x4u_durations", store=True, aggregator="avg", string="Purchasing (days)")
    x4u_days_approval = fields.Float(compute="_compute_x4u_durations", store=True, aggregator="avg", string="Approval (days)")
    x4u_days_supplier = fields.Float(compute="_compute_x4u_durations", store=True, aggregator="avg", string="Supplier delivery (days)")
    x4u_days_warehouse = fields.Float(compute="_compute_x4u_durations", store=True, aggregator="avg", string="Warehouse issue (days)")
    x4u_days_assembly = fields.Float(compute="_compute_x4u_durations", store=True, aggregator="avg", string="Assembly & test (days)")
    x4u_days_qc = fields.Float(compute="_compute_x4u_durations", store=True, aggregator="avg", string="QC (days)")
    x4u_days_dispatch = fields.Float(compute="_compute_x4u_durations", store=True, aggregator="avg", string="Dispatch (days)")
    x4u_days_total = fields.Float(compute="_compute_x4u_durations", store=True, aggregator="avg", string="Total (days)")
    x4u_delay_stage = fields.Selection(
        [(key, label) for key, label, _starts, _end in STAGES],
        string="Delay At",
        compute="_compute_x4u_durations",
        store=True,
        index=True,
    )
    x4u_delay_days = fields.Float(compute="_compute_x4u_durations", store=True, string="Delay (days)")

    @api.model
    def _read_group_x4u_job_state(self, values, domain):
        return [key for key, _label in JOB_STATES if key != "cancelled"]

    @api.depends("product_id.x4u_is_generator")
    def _compute_x4u_is_job_order(self):
        for production in self:
            production.x4u_is_job_order = production.product_id.x4u_is_generator

    @api.depends("sale_line_id.order_id", "procurement_group_id.sale_id")
    def _compute_x4u_sale_order(self):
        # sale_line_id is there from creation; the group's sale only after confirmation.
        for production in self:
            production.x4u_sale_order_id = production.sale_line_id.order_id or production.procurement_group_id.sale_id

    def _compute_x4u_documents(self):
        for production in self:
            production.x4u_request_count = len(production._x4u_purchase_requests())

    @api.depends("move_raw_ids.state")
    def _compute_x4u_parts(self):
        labels = dict(self.env["stock.move"]._fields["x4u_part_status"]._description_selection(self.env))
        for production in self:
            for role in PART_ROLES:
                move = production.move_raw_ids.filtered(lambda m, r=role: m.x4u_role == r)[:1]
                text = False
                if move:
                    text = labels.get(move.x4u_part_status) or ""
                    if move.x4u_purchase_id:
                        text = "%s · %s" % (move.x4u_purchase_id.name, text)
                        if move.x4u_part_status in ("rfq", "ordered") and move.x4u_expected_date:
                            text += " · %s" % move.x4u_expected_date.strftime("%d/%m")
                production["x4u_%s_status" % role] = text

    @api.depends("x4u_event_ids.date", "x4u_event_ids.event_type", "x4u_job_state")
    def _compute_x4u_durations(self):
        params = self.env["ir.config_parameter"].sudo()
        targets = {key: float(params.get_param("x4u_job_order.target_%s_days" % key) or 0.0) for key in STAGE_KEYS}
        now = fields.Datetime.now()
        for production in self:
            events = production.x4u_event_ids
            dates = {}
            for event in events:
                dates.setdefault(event.event_type, []).append(event.date)

            def first(types):
                found = [d for t in types for d in dates.get(t, [])]
                return min(found) if found else None

            def last(types):
                found = [d for t in types for d in dates.get(t, [])]
                return max(found) if found else None

            delay_stage, delay_days = False, 0.0
            closed = production.x4u_job_state in ("finished", "cancelled")
            for index, (key, _label, starts, end) in enumerate(STAGES):
                start = last(starts)
                finish = (first if end in SINGLE_EVENTS else last)((end,))
                done = bool(start and finish and finish >= start)
                production["x4u_days_" + key] = round((finish - start).total_seconds() / 86400, 2) if done else 0.0
                if delay_stage or not targets[key] or not start:
                    continue
                if done:
                    elapsed = (finish - start).total_seconds() / 86400
                else:
                    later_started = any(last(stage[2]) for stage in STAGES[index + 1:])
                    if closed or later_started:
                        continue
                    elapsed = (now - start).total_seconds() / 86400
                if elapsed > targets[key]:
                    delay_stage, delay_days = key, round(elapsed - targets[key], 1)
            opened = first(("order_opened", "job_order_created"))
            delivered = first(("delivered",))
            production.x4u_days_total = (
                round((delivered - opened).total_seconds() / 86400, 2) if opened and delivered else 0.0
            )
            production.x4u_delay_stage = delay_stage
            production.x4u_delay_days = delay_days

    # ------------------------------------------------------------------
    # Links to the documents of the Job Order
    # ------------------------------------------------------------------
    def _x4u_component_moves(self):
        """Moves that bring each part to the factory (Pick Components), or the raw moves."""
        pick_moves = self.move_raw_ids.move_orig_ids.filtered(lambda m: m.state != "cancel")
        return pick_moves or self.move_raw_ids

    def _x4u_purchase_requests(self):
        lines = self.env["purchase.request.line"].sudo().search(
            [("move_dest_ids", "in", self._x4u_component_moves().ids)]
        )
        return lines.request_id

    @api.model
    def _x4u_from_moves(self, moves):
        """Job Orders that the given moves feed, following the move chain."""
        productions = self.browse()
        for _depth in range(3):
            if not moves:
                break
            productions |= moves.raw_material_production_id
            moves = moves.move_dest_ids
        return productions.filtered("x4u_is_job_order")

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------
    def _x4u_log(self, event_type, document=None, detail=None, date=None):
        """Record one step of the Job Order (idempotent per step / document)."""
        Event = self.env["x4u.job.order.event"].sudo()
        for production in self.filtered("x4u_is_job_order"):
            existing = production.sudo().x4u_event_ids.filtered(lambda e: e.event_type == event_type)
            if event_type in SINGLE_EVENTS and existing:
                continue
            if document and existing.filtered(lambda e: e.document == document and e.detail == (detail or False)):
                continue
            Event.create(
                {
                    "production_id": production.id,
                    "event_type": event_type,
                    "date": date or fields.Datetime.now(),
                    "user_id": self.env.user.id,
                    "document": "%s,%s" % (document._name, document.id) if document else False,
                    "detail": detail or False,
                }
            )

    def _x4u_notify(self, role, summary):
        """Activity for the person in charge of this step (Settings › 4U Job Orders)."""
        user_id = int(self.env["ir.config_parameter"].sudo().get_param("x4u_job_order.%s_user_id" % role) or 0)
        if user_id:
            for production in self:
                production.sudo().activity_schedule("mail.mail_activity_data_todo", user_id=user_id, summary=summary)

    def _x4u_set_state(self, state):
        self.filtered("x4u_is_job_order").sudo().write({"x4u_job_state": state})

    def _x4u_check_parts_ready(self):
        for production in self.filtered(lambda p: p.x4u_job_state == "waiting_parts"):
            moves = production._x4u_component_moves()
            if moves and all(move.state in ("assigned", "done") for move in moves):
                production._x4u_set_state("parts_ready")
                production._x4u_log("parts_ready")
                production._x4u_notify("warehouse", _("Deliver the material for %s", production.name))

    # ------------------------------------------------------------------
    # Serial and generator card
    # ------------------------------------------------------------------
    def _x4u_assign_serial(self):
        """The generator serial is the Job Order number (spec §6 S1)."""
        for production in self:
            if production.product_id.tracking != "serial" or production.lot_producing_id:
                continue
            production.lot_producing_id = self.env["stock.lot"].create(
                {
                    "name": production.name,
                    "product_id": production.product_id.id,
                    "company_id": production.company_id.id,
                }
            )

    def _x4u_fill_generator_card(self):
        """Card gets the sale, the customer and the chosen variant (spec §6 S2)."""
        enclosure_attr = self.env.ref("x4u_setup_base.attr_enclosure", raise_if_not_found=False)
        alternator_attr = self.env.ref("x4u_setup_base.attr_alternator", raise_if_not_found=False)
        for production in self:
            card = production.lot_producing_id.sudo().x4u_generator_id
            if not card:
                continue
            vals = {}
            sale = production.x4u_sale_order_id
            if sale:
                vals.update(sale_order_id=sale.id, customer_id=sale.partner_id.commercial_partner_id.id)
            for ptav in production.product_id.product_template_attribute_value_ids:
                value = ptav.product_attribute_value_id
                if value.attribute_id == enclosure_attr:
                    vals["x4u_enclosure"] = value.name
                elif value.attribute_id == alternator_attr:
                    brand = self.env["x4u.generator.brand"].sudo().search([("name", "=ilike", value.name)], limit=1)
                    if brand:
                        vals["alternator_brand_id"] = brand.id
            alternator = production.move_raw_ids.filtered(lambda m: m.x4u_role == "alternator")[:1].product_id
            if alternator:
                vals["alternator_model"] = alternator.default_code or alternator.name
            if vals:
                card.write(vals)

    # ------------------------------------------------------------------
    # Workflow hooks
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        productions = super().create(vals_list)
        for production in productions.filtered("x4u_is_job_order"):
            production._x4u_log("job_order_created", document=production)
        return productions

    def action_confirm(self):
        res = super().action_confirm()
        for production in self.filtered(lambda p: p.x4u_is_job_order and p.state not in ("draft", "cancel")):
            production._x4u_assign_serial()
            production._x4u_fill_generator_card()
            if not production.x4u_job_state:
                production._x4u_set_state("waiting_parts")
            requests = production._x4u_purchase_requests()
            # The only approval is the GM's on the purchase order (spec §5 P6).
            requests.filtered(lambda r: r.state in ("draft", "to_approve")).sudo().button_approved()
            for request in requests:
                production._x4u_log("material_request", document=request, date=request.create_date)
            if requests:
                production._x4u_notify("purchase", _("Order the material for %s", production.name))
            production._x4u_check_parts_ready()
        return res

    def button_mark_done(self):
        res = super().button_mark_done()
        for production in self.filtered(lambda p: p.x4u_is_job_order and p.state == "done"):
            production._x4u_set_state("assembled")
            production._x4u_log("assembled", document=production, date=production.date_finished)
            production._x4u_notify("qc", _("Inspect generator %s before delivery", production.name))
        return res

    def action_cancel(self):
        res = super().action_cancel()
        self.filtered(lambda p: p.state == "cancel")._x4u_set_state("cancelled")
        return res

    @api.model
    def _cron_x4u_update_delays(self):
        """Ongoing stages get longer every day: refresh "Delay At" daily."""
        open_jobs = self.search([("x4u_is_job_order", "=", True), ("x4u_job_state", "not in", ("finished", "cancelled"))])
        self.env.add_to_compute(self._fields["x4u_delay_stage"], open_jobs)
        open_jobs.flush_recordset(["x4u_delay_stage", "x4u_delay_days"])

    # ------------------------------------------------------------------
    # Smart buttons
    # ------------------------------------------------------------------
    def action_x4u_open_requests(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("purchase_request.purchase_request_form_action")
        action["domain"] = [("id", "in", self._x4u_purchase_requests().ids)]
        action["context"] = {"create": False}
        return action

    def action_x4u_open_sale(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": self.x4u_sale_order_id.id,
            "view_mode": "form",
        }

    def action_x4u_open_generator(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "x4u.generator",
            "res_id": self.x4u_generator_id.id,
            "view_mode": "form",
        }
