import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# A UAE Tax Registration Number: 15 digits (spaces and dashes allowed when typed).
TRN_RE = re.compile(r"^\d{15}$")


def clean_trn(vat):
    return re.sub(r"[\s-]", "", vat or "")


class ResPartner(models.Model):
    _inherit = "res.partner"

    x4u_vat_registered = fields.Boolean(
        string="VAT Registered (UAE)", compute="_compute_x4u_vat_registered", store=True, readonly=False,
        help="Registered for VAT in the UAE: its TRN is required to confirm an invoice or bill (spec §21 V2). "
        "Ticked by itself when a UAE contact has a TRN; tick it for a registered company whose TRN is not in yet.",
    )

    @api.depends("vat", "country_id")
    def _compute_x4u_vat_registered(self):
        # Never unticked here: a registered company that loses its TRN must get it back, not slip through.
        for partner in self:
            has_trn = bool(partner.vat and partner.country_id.code == "AE")
            partner.x4u_vat_registered = has_trn or partner.x4u_vat_registered

    @api.model
    def _commercial_fields(self):
        return super()._commercial_fields() + ["x4u_vat_registered"]

    @api.constrains("vat", "country_id")
    def _check_x4u_trn(self):
        """Spec §21 V1: a UAE contact's TRN is 15 digits. A foreign vendor's VAT number keeps its own format."""
        for partner in self:
            if partner.vat and partner.country_id.code == "AE" and not TRN_RE.match(clean_trn(partner.vat)):
                raise ValidationError(
                    _("The TRN of %(partner)s must be 15 digits (it is %(vat)s).", partner=partner.display_name, vat=partner.vat)
                )
