from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    x4u_document_prefix = fields.Char(
        string="Document Prefix",
        help="Company code at the start of document numbers, e.g. 4U gives invoices 4U-INV-2026-0001.",
    )
