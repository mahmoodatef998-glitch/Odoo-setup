from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Card field -> product field, copied when the card is created (spec D2).
PRODUCT_SPEC_FIELDS = {
    "kva_prime": "x4u_kva_prime",
    "kva_standby": "x4u_kva_standby",
    "engine_brand_id": "x4u_engine_brand_id",
    "engine_model": "x4u_engine_model",
    "alternator_brand_id": "x4u_alternator_brand_id",
    "alternator_model": "x4u_alternator_model",
    "warranty_months": "x4u_warranty_months",
    "warranty_hours": "x4u_warranty_hours",
    "warranty_max_delivery_months": "x4u_warranty_max_delivery_months",
}

# Fields filled on delivery to a customer and cleared on return (R4/R5).
DELIVERY_FIELDS = (
    "customer_id",
    "site_address_id",
    "sale_order_id",
    "delivery_picking_id",
    "delivery_date",
    "commissioning_date",
)


class X4uGenerator(models.Model):
    _name = "x4u.generator"
    _description = "Generator Card"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name, id"
    _check_company_auto = True

    name = fields.Char(
        string="Serial No", related="lot_id.name", store=True, index="trigram"
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot/Serial Number",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
        check_company=True,
        domain="[('product_id.x4u_is_generator', '=', True),"
        " ('x4u_generator_ids', '=', False)]",
    )
    product_id = fields.Many2one(related="lot_id.product_id", store=True, index=True)
    # Not related to lot_id.company_id: lots of products shared between companies
    # have no company in Odoo 18, and the card must still belong to one.
    company_id = fields.Many2one(
        "res.company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)

    # Specs
    kva_prime = fields.Float(string="Prime Rating (kVA)", required=True, tracking=True)
    kva_standby = fields.Float(string="Standby Rating (kVA)", tracking=True)
    engine_brand_id = fields.Many2one(
        "x4u.generator.brand",
        string="Engine Brand",
        domain="[('brand_type', 'in', ('engine', 'both'))]",
        tracking=True,
    )
    engine_model = fields.Char(tracking=True)
    engine_serial = fields.Char(string="Engine Serial No", tracking=True, copy=False)
    alternator_brand_id = fields.Many2one(
        "x4u.generator.brand",
        string="Alternator Brand",
        domain="[('brand_type', 'in', ('alternator', 'both'))]",
        tracking=True,
    )
    alternator_model = fields.Char(tracking=True)
    alternator_serial = fields.Char(
        string="Alternator Serial No", tracking=True, copy=False
    )

    # Sale & delivery
    state = fields.Selection(
        [
            ("in_stock", "In Stock"),
            ("delivered", "Delivered"),
            ("commissioned", "Commissioned"),
        ],
        compute="_compute_state",
        store=True,
        index=True,
        tracking=True,
    )
    customer_id = fields.Many2one(
        "res.partner", string="Customer", index=True, tracking=True
    )
    site_address_id = fields.Many2one(
        "res.partner", string="Site / Delivery Address", tracking=True
    )
    sale_order_id = fields.Many2one(
        "sale.order", string="Sales Order", index=True, tracking=True
    )
    delivery_picking_id = fields.Many2one(
        "stock.picking", string="Delivery Order", tracking=True
    )
    delivery_date = fields.Date(tracking=True)
    commissioning_date = fields.Date(
        tracking=True, help="Date the generator was put into service at the site."
    )

    # Running hours
    hour_reading_ids = fields.One2many(
        "x4u.generator.hour.reading", "generator_id", string="Running Hours Readings"
    )
    running_hours = fields.Float(compute="_compute_running_hours", store=True)
    last_reading_date = fields.Datetime(compute="_compute_running_hours", store=True)

    # Warranty
    warranty_months = fields.Integer(string="Warranty (Months)", tracking=True)
    warranty_hours = fields.Float(
        string="Warranty (Running Hours)",
        help="0 means no running-hours limit.",
        tracking=True,
    )
    warranty_max_delivery_months = fields.Integer(
        string="Max Warranty from Delivery (Months)",
        help="Optional cap: the warranty also ends this many months after delivery, "
        "whichever comes first. 0 means no cap.",
        tracking=True,
    )
    warranty_start_date = fields.Date(
        compute="_compute_warranty_start_date",
        store=True,
        readonly=False,
        tracking=True,
        help="Commissioning date if set, otherwise delivery date.",
    )
    warranty_end_date = fields.Date(
        compute="_compute_warranty_end_date", store=True, tracking=True
    )
    warranty_state = fields.Selection(
        [
            ("not_started", "Not Started"),
            ("active", "Active"),
            ("expired", "Expired"),
        ],
        compute="_compute_warranty_state",
        store=True,
        index=True,
        tracking=True,
    )

    # Quality
    qc_inspection_ids = fields.One2many(
        related="lot_id.qc_inspections_ids", string="Inspections"
    )
    qc_inspection_count = fields.Integer(compute="_compute_qc_inspection_count")
    qc_state = fields.Selection(
        [
            ("none", "No Inspection"),
            ("pending", "Pending"),
            ("passed", "Passed"),
            ("failed", "Failed"),
        ],
        string="QC Status",
        compute="_compute_qc_state",
        store=True,
        index=True,
        tracking=True,
    )

    note = fields.Html()

    _sql_constraints = [
        (
            "lot_uniq",
            "unique(lot_id)",
            "A generator card already exists for this serial number.",
        ),
    ]

    @api.depends("delivery_date", "commissioning_date")
    def _compute_state(self):
        for card in self:
            if card.delivery_date and card.commissioning_date:
                card.state = "commissioned"
            elif card.delivery_date:
                card.state = "delivered"
            else:
                card.state = "in_stock"

    @api.depends("hour_reading_ids.hours", "hour_reading_ids.date")
    def _compute_running_hours(self):
        # Readings can't go backwards (R7), so the latest reading is the highest.
        for card in self:
            readings = card.hour_reading_ids
            card.running_hours = max(readings.mapped("hours"), default=0.0)
            card.last_reading_date = max(
                (date for date in readings.mapped("date") if date), default=False
            )

    @api.depends("commissioning_date", "delivery_date")
    def _compute_warranty_start_date(self):
        for card in self:
            card.warranty_start_date = card.commissioning_date or card.delivery_date

    @api.depends(
        "warranty_start_date",
        "warranty_months",
        "delivery_date",
        "warranty_max_delivery_months",
    )
    def _compute_warranty_end_date(self):
        for card in self:
            if not card.warranty_start_date:
                card.warranty_end_date = False
                continue
            end = card.warranty_start_date + relativedelta(months=card.warranty_months)
            if card.warranty_max_delivery_months and card.delivery_date:
                end = min(
                    end,
                    card.delivery_date
                    + relativedelta(months=card.warranty_max_delivery_months),
                )
            card.warranty_end_date = end

    @api.depends(
        "warranty_start_date", "warranty_end_date", "warranty_hours", "running_hours"
    )
    def _compute_warranty_state(self):
        # Depends on today too: _cron_update_warranty_state recomputes it daily.
        today = fields.Date.context_today(self)
        for card in self:
            expired_by_date = card.warranty_end_date and today > card.warranty_end_date
            expired_by_hours = (
                card.warranty_hours and card.running_hours >= card.warranty_hours
            )
            if not card.warranty_start_date:
                card.warranty_state = "not_started"
            elif expired_by_date or expired_by_hours:
                card.warranty_state = "expired"
            else:
                card.warranty_state = "active"

    @api.depends("lot_id.qc_inspections_ids")
    def _compute_qc_inspection_count(self):
        for card in self:
            card.qc_inspection_count = len(card.lot_id.sudo().qc_inspections_ids)

    @api.depends("lot_id.qc_inspections_ids.state", "lot_id.qc_inspections_ids.date")
    def _compute_qc_state(self):
        result_map = {"success": "passed", "failed": "failed"}
        for card in self:
            inspections = card.lot_id.sudo().qc_inspections_ids.filtered(
                lambda inspection: inspection.state != "canceled"
            )
            if not inspections:
                card.qc_state = "none"
                continue
            last = inspections.sorted(lambda insp: (insp.date, insp.id))[-1]
            card.qc_state = result_map.get(last.state, "pending")

    @api.constrains("kva_prime", "kva_standby")
    def _check_kva(self):
        for card in self:
            if card.kva_prime <= 0:
                raise ValidationError(
                    _(
                        "Prime rating (kVA) of generator %s must be greater than zero.",
                        card.display_name,
                    )
                )
            if card.kva_standby < 0:
                raise ValidationError(
                    _(
                        "Standby rating (kVA) of generator %s can't be negative.",
                        card.display_name,
                    )
                )

    @api.constrains("warranty_months", "warranty_hours", "warranty_max_delivery_months")
    def _check_warranty_terms(self):
        for card in self:
            if min(
                card.warranty_months,
                card.warranty_hours,
                card.warranty_max_delivery_months,
            ) < 0:
                raise ValidationError(
                    _(
                        "Warranty terms of generator %s can't be negative.",
                        card.display_name,
                    )
                )

    @api.constrains("commissioning_date", "delivery_date")
    def _check_commissioning_date(self):
        for card in self.filtered("commissioning_date"):
            if not card.delivery_date:
                raise ValidationError(
                    _(
                        "Generator %s can't be commissioned before it is delivered.",
                        card.display_name,
                    )
                )
            if card.commissioning_date < card.delivery_date:
                raise ValidationError(
                    _(
                        "Commissioning date of generator %s can't be before "
                        "its delivery date.",
                        card.display_name,
                    )
                )

    @api.model
    def _prepare_values_from_lot(self, lot):
        product = lot.product_id
        values = {}
        for card_field, product_field in PRODUCT_SPEC_FIELDS.items():
            value = product[product_field]
            values[card_field] = value.id if isinstance(value, models.BaseModel) else value
        if lot.company_id:
            values["company_id"] = lot.company_id.id
        return values

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("lot_id"):
                lot = self.env["stock.lot"].browse(vals["lot_id"])
                for key, value in self._prepare_values_from_lot(lot).items():
                    vals.setdefault(key, value)
        return super().create(vals_list)

    @api.onchange("lot_id")
    def _onchange_lot_id(self):
        if self.lot_id:
            self.update(self._prepare_values_from_lot(self.lot_id))

    @api.model
    def _cron_update_warranty_state(self):
        cards = self.with_context(active_test=False).search(
            [("warranty_state", "=", "active")]
        )
        self.env.add_to_compute(self._fields["warranty_state"], cards)
        cards.flush_recordset(["warranty_state"])

    def _x4u_open_form(self, record, name):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": record._name,
            "res_id": record.id,
            "view_mode": "form",
        }

    def action_open_lot(self):
        return self._x4u_open_form(self.lot_id, _("Lot/Serial Number"))

    def action_open_sale_order(self):
        return self._x4u_open_form(self.sale_order_id, _("Sales Order"))

    def action_open_delivery(self):
        return self._x4u_open_form(self.delivery_picking_id, _("Delivery Order"))

    def action_open_inspections(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "quality_control_oca.action_qc_inspection"
        )
        action["domain"] = [("lot_id", "=", self.lot_id.id)]
        action["context"] = {"default_object_id": f"stock.lot,{self.lot_id.id}"}
        return action
