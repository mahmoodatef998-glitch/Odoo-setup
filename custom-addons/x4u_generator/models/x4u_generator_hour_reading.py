from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class X4uGeneratorHourReading(models.Model):
    _name = "x4u.generator.hour.reading"
    _description = "Generator Running Hours Reading"
    _order = "date desc, id desc"

    generator_id = fields.Many2one(
        "x4u.generator",
        string="Generator",
        required=True,
        ondelete="cascade",
        index=True,
    )
    date = fields.Datetime(required=True, default=fields.Datetime.now)
    hours = fields.Float(string="Running Hours", required=True)
    source = fields.Selection(
        [
            ("factory_test", "Factory Test"),
            ("commissioning", "Commissioning"),
            ("service", "Service Visit"),
            ("customer", "Customer Report"),
            ("other", "Other"),
        ],
        required=True,
        default="service",
    )
    user_id = fields.Many2one(
        "res.users", string="Recorded By", default=lambda self: self.env.user
    )
    note = fields.Char()
    company_id = fields.Many2one(
        related="generator_id.company_id", store=True, index=True
    )

    @api.constrains("hours", "date", "generator_id")
    def _check_hours(self):
        for reading in self:
            if reading.hours < 0:
                raise ValidationError(_("Running hours can't be negative."))
            others = reading.generator_id.hour_reading_ids - reading
            earlier_max = max(
                others.filtered(lambda r: r.date < reading.date).mapped("hours"),
                default=None,
            )
            later_min = min(
                others.filtered(lambda r: r.date > reading.date).mapped("hours"),
                default=None,
            )
            if (earlier_max is not None and reading.hours < earlier_max) or (
                later_min is not None and reading.hours > later_min
            ):
                raise ValidationError(
                    _(
                        "Reading of %(hours)s hours on %(date)s for generator "
                        "%(generator)s is out of sequence: the hour meter can't "
                        "go backwards.",
                        hours=reading.hours,
                        date=reading.date,
                        generator=reading.generator_id.display_name,
                    )
                )
