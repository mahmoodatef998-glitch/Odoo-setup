from odoo import _, api, fields, models

TRIGGERS = [
    ("order", "With Order"),
    ("progress", "Progress"),
    ("shipment", "Before Shipment"),
    ("delivery", "Before Delivery"),
    ("invoice", "After Invoice"),
]
# Paid before the goods leave: the Accountant's to-do when the generator is ready.
BEFORE_DELIVERY = ("order", "progress", "shipment", "delivery")
LINE_STATES = [("not_paid", "Not Paid"), ("partial", "Partially Paid"), ("paid", "Paid")]


class X4uPaymentScheduleMixin(models.AbstractModel):
    """One payment agreed with the customer or the vendor (spec §6 S3, x4u_purchase P4).

    The concrete models add `order_id` (whose `x4u_schedule_ids` they are), and the vendor
    schedule its `proforma_id`; the order gives `_x4u_amount_received()`.
    """

    _name = "x4u.payment.schedule.mixin"
    _description = "Payment Schedule Line"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    percent = fields.Float(string="%", digits=(16, 2), required=True)
    trigger = fields.Selection(TRIGGERS, string="When", required=True, default="order")
    days = fields.Integer(help="After Invoice: how many days after the invoice date.")
    date_due = fields.Date(string="Due Date")
    currency_id = fields.Many2one("res.currency")
    amount_untaxed = fields.Monetary(string="Before VAT", compute="_compute_x4u_amounts")
    amount_tax = fields.Monetary(string="VAT", compute="_compute_x4u_amounts")
    amount_total = fields.Monetary(string="Amount", compute="_compute_x4u_amounts")
    amount_paid = fields.Monetary(string="Paid", compute="_compute_x4u_amounts")
    state = fields.Selection(LINE_STATES, string="Status", compute="_compute_x4u_amounts")

    _sql_constraints = [
        ("x4u_percent_positive", "CHECK(percent > 0)", "Each payment needs a percentage above 0."),
        ("x4u_days_positive", "CHECK(days >= 0)", "The days after the invoice cannot be negative."),
    ]

    def _compute_x4u_amounts(self):
        """The order split by percent (the last line takes the rounding), then what came in, in order."""
        values = {}
        for order in self.order_id:
            currency = order.currency_id
            lines = order.x4u_schedule_ids
            whole = currency.is_zero(sum(lines.mapped("percent")) - 100.0)
            untaxed_left, tax_left = order.amount_untaxed, order.amount_tax
            received = order._x4u_amount_received()
            for index, line in enumerate(lines):
                if whole and index == len(lines) - 1:
                    untaxed, tax = untaxed_left, tax_left
                else:
                    untaxed = currency.round(order.amount_untaxed * line.percent / 100.0)
                    tax = currency.round(order.amount_tax * line.percent / 100.0)
                untaxed_left -= untaxed
                tax_left -= tax
                total = untaxed + tax
                paid = min(received, total)
                received -= paid
                if total and currency.compare_amounts(paid, total) >= 0:
                    state = "paid"
                elif not currency.is_zero(paid):
                    state = "partial"
                else:
                    state = "not_paid"
                values[line] = (untaxed, tax, total, paid, state)
        for line in self:
            untaxed, tax, total, paid, state = values.get(line, (0.0, 0.0, 0.0, 0.0, "not_paid"))
            line.amount_untaxed = untaxed
            line.amount_tax = tax
            line.amount_total = total
            line.amount_paid = paid
            line.state = state

    def _x4u_label(self):
        """'30% With Order', '100% After Invoice 60 days': for the chatter and the PDF."""
        self.ensure_one()
        when = dict(self._fields["trigger"]._description_selection(self.env))[self.trigger]
        if self.trigger == "invoice" and self.days:
            when = _("%(when)s %(days)s days", when=when, days=self.days)
        return "%g%% %s" % (self.percent, when)

    @api.model
    def _x4u_values_from_term(self, term):
        """The lines of a standard payment term: advances first, the last one before delivery."""
        lines = term.line_ids.filtered(lambda line: line.value == "percent").sorted("id")
        values = []
        for index, line in enumerate(lines):
            if not term.x4u_pay_before_delivery:
                trigger = "invoice"
            elif index == 0:
                trigger = "order"
            elif index == len(lines) - 1:
                trigger = "delivery"
            else:
                trigger = "progress"
            values.append(
                {
                    "sequence": (index + 1) * 10,
                    "percent": line.value_amount,
                    "trigger": trigger,
                    "days": line.nb_days if trigger == "invoice" else 0,
                }
            )
        return values


class X4uSaleSchedule(models.Model):
    _name = "x4u.sale.schedule"
    _inherit = "x4u.payment.schedule.mixin"
    _description = "Sales Payment Schedule"

    order_id = fields.Many2one("sale.order", string="Sales Order", required=True, ondelete="cascade", index=True)
    currency_id = fields.Many2one(related="order_id.currency_id")

    @api.depends(
        "percent",
        "sequence",
        "order_id.x4u_schedule_ids",
        "order_id.amount_untaxed",
        "order_id.amount_tax",
        "order_id.x4u_amount_remaining",
    )
    def _compute_x4u_amounts(self):
        return super()._compute_x4u_amounts()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._x4u_check_change(set().union(*vals_list))
        return lines

    def write(self, vals):
        self._x4u_check_change(set(vals))
        res = super().write(vals)
        if "date_due" in vals:
            self.sudo().order_id._x4u_sync_followup()
        return res

    def unlink(self):
        self._x4u_check_change({"percent"})
        return super().unlink()

    def _x4u_check_change(self, changed):
        """Salespeople write the Custom schedule before the order is locked; the Accountant
        only sets the due dates (S3, S12). The order's own changes skip this (sync)."""
        if self.env.context.get("x4u_schedule_sync") or self.env.su:
            return
        if changed <= {"date_due"}:
            if not self.env.user.has_group("account.group_account_invoice"):
                raise self.env["sale.order"]._x4u_accountant_only()
            return
        for order in self.order_id:
            order._x4u_check_schedule_editable()
