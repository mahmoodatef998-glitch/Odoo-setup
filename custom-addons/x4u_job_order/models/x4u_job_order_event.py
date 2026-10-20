from odoo import _, api, fields, models
from odoo.exceptions import UserError

EVENT_TYPES = [
    ("order_opened", "Order opened"),
    ("job_order_created", "Job Order created"),
    ("material_request", "Material request created"),
    ("rfq_created", "RFQ created"),
    ("po_approved", "PO approved"),
    ("po_sent", "PO sent to supplier"),
    ("part_received", "Part received"),
    ("parts_ready", "Parts ready"),
    ("material_delivered", "Material delivered to factory"),
    ("assembled", "Assembled & tested"),
    ("qc_passed", "QC passed"),
    ("qc_failed", "QC failed"),
    ("delivered", "Delivered to customer"),
]

# Logged once per Job Order; the others repeat (one per PO, part or inspection).
SINGLE_EVENTS = {
    "order_opened",
    "job_order_created",
    "material_request",
    "parts_ready",
    "material_delivered",
    "assembled",
    "delivered",
}


class X4uJobOrderEvent(models.Model):
    """One step of a Job Order: when, who and which document (spec §7.1).

    Written by the code only; nobody can change or delete it from the UI,
    so the timeline stays trustworthy.
    """

    _name = "x4u.job.order.event"
    _description = "Job Order Event"
    _order = "date, id"

    production_id = fields.Many2one(
        "mrp.production", string="Job Order", required=True, ondelete="cascade", index=True
    )
    event_type = fields.Selection(EVENT_TYPES, string="Event", required=True, index=True)
    date = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    user_id = fields.Many2one("res.users", string="Done By", default=lambda self: self.env.user)
    document = fields.Reference(selection="_selection_document")
    detail = fields.Char()
    company_id = fields.Many2one(related="production_id.company_id", store=True, index=True)

    @api.model
    def _selection_document(self):
        models_ = ("sale.order", "mrp.production", "purchase.request", "purchase.order", "stock.picking", "qc.inspection")
        return [(name, self.env[name]._description) for name in models_ if name in self.env]

    def write(self, vals):
        if not self.env.su:
            raise UserError(_("Job Order events can't be changed."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(_("Job Order events can't be deleted."))
        return super().unlink()
