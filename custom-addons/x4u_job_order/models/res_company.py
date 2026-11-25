from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # x4u_generator_datasheet §9 / x4u_reports §2: the 4U letterhead of the quotation (QT 1112). The
    # images carry the company's details, so they are uploaded to the database, never kept in Git.
    x4u_letterhead_header = fields.Image(
        string="Letterhead Header", max_width=2600, max_height=400,
        help="Top of every page of the 4U quotation: names in English and Arabic, logo, contact line.",
    )
    x4u_letterhead_footer = fields.Image(
        string="Letterhead Brands", max_width=2600, max_height=400,
        help="Bottom of every page of the 4U quotation: the brands (Baudouin, Perkins, Leroy-Somer...).",
    )
