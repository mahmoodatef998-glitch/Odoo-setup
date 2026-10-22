from odoo import fields, models

# Account codes are the same numbers in both companies; the company shows on the
# documents instead (docs/modules/06-accounting.md).
KINDS = {"out_invoice": "INV", "out_refund": "CN"}


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_starting_sequence(self):
        """Customer invoices 4U-INV-2026-0001 and credit notes 4U-CN-2026-0001.

        Odoo only builds the first number of a year; the next ones follow its format,
        and the yearly reset keeps working because the year is in the number.
        """
        prefix = self.company_id.x4u_document_prefix
        if prefix and self.journal_id.type == "sale" and self.move_type in KINDS:
            move_date = self.date or self.invoice_date or fields.Date.context_today(self)
            return "%s-%s-%04d-0000" % (prefix, KINDS[self.move_type], move_date.year)
        return super()._get_starting_sequence()
