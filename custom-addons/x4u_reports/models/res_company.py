from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # x4u_reports §2: the 4U letterhead of every printed document. The texts and the images carry
    # the company's details, so they live in the database (Settings › Companies › 4U Letterhead, or
    # scripts/set_letterhead.py from the git-ignored private/branding/), never in Git.
    x4u_lh_name = fields.Char(
        "Letterhead Name", help="Top left of every page, e.g. the company's name in capitals."
    )
    x4u_lh_tagline = fields.Char("Letterhead Activity", help="Under the name: what the company does.")
    x4u_lh_name_ar = fields.Char("Letterhead Name (Arabic)", help="Top right of every page.")
    x4u_lh_tagline_ar = fields.Char("Letterhead Activity (Arabic)")
    x4u_lh_contact = fields.Char(
        "Contact Line",
        help="The line under the names: phone, mobile, email, address, TRN. "
        "Empty: built from the company's phone, mobile, email, address and Tax ID.",
    )
    x4u_lh_logo = fields.Image(
        "Letterhead Logo", max_width=1600, max_height=800,
        help="In the middle of the header, transparent background.",
    )
    x4u_lh_watermark = fields.Image(
        "Watermark", max_width=1600, max_height=2000,
        help="In the middle of every page, behind the text: a light picture (transparent PNG).",
    )
    x4u_lh_brands = fields.Image(
        "Brands", max_width=3000, max_height=400,
        help="At the bottom of every page, between two yellow lines.",
    )
    x4u_lh_ready = fields.Boolean(
        compute="_compute_x4u_lh_ready",
        help="The company has a letterhead: the 4U layout draws it, otherwise the standard layout.",
    )

    @api.depends("x4u_lh_name", "x4u_lh_logo")
    def _compute_x4u_lh_ready(self):
        for company in self:
            company.x4u_lh_ready = bool(company.x4u_lh_name or company.x4u_lh_logo)

    def _x4u_lh_contact_line(self):
        """The contact line of the letterhead: the typed one, else from the company's details."""
        self.ensure_one()
        if self.x4u_lh_contact:
            return self.x4u_lh_contact
        address = ", ".join(
            part for part in (self.street, self.street2, self.city, self.country_id.name) if part
        )
        parts = [
            self.phone and "Tel: %s" % self.phone,
            self.mobile and "Mob: %s" % self.mobile,
            self.email and "E-mail: %s" % self.email,
            address,
            self.vat and "%s: %s" % (self.country_id.vat_label or "TRN", self.vat),
        ]
        return ", ".join(part for part in parts if part)
