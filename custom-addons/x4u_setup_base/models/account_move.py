from odoo import fields, models

# Account codes are the same numbers in both companies; the company shows on the
# documents instead (docs/modules/06-accounting.md). Vendor bills too (UAT Phase 3, 2026-11-25).
KINDS = {
    "out_invoice": ("sale", "INV"),
    "out_refund": ("sale", "CN"),
    "in_invoice": ("purchase", "BILL"),
    "in_refund": ("purchase", "VCN"),
}


class AccountMove(models.Model):
    _inherit = "account.move"

    def _x4u_number_prefix(self):
        """'4U-BILL-2026-' for a 4U vendor bill of 2026, None when Odoo's own numbering applies."""
        self.ensure_one()
        company_prefix = self.company_id.x4u_document_prefix
        journal_type, kind = KINDS.get(self.move_type, (None, None))
        if not company_prefix or not kind or self.journal_id.type != journal_type:
            return None
        move_date = self.date or self.invoice_date or fields.Date.context_today(self)
        return "%s-%s-%04d-" % (company_prefix, kind, move_date.year)

    def _get_starting_sequence(self):
        """Invoices 4U-INV-2026-0001, credit notes 4U-CN-2026-0001, vendor bills 4U-BILL-2026-0001,
        vendor credit notes 4U-VCN-2026-0001.

        Odoo only builds the first number of a year; the next ones follow its format,
        and the yearly reset keeps working because the year is in the number.
        """
        prefix = self._x4u_number_prefix()
        if prefix:
            return prefix + "0000"
        return super()._get_starting_sequence()

    def _get_last_sequence(self, relaxed=False, with_prefix=None):
        """The last number of the same kind and year, ignoring Odoo's older format in the journal.

        A journal that already has BILL/2026/11/00001 would otherwise go on with it. The year is
        in the prefix, so the whole year is searched (relaxed) and nothing else changes for it.
        """
        prefix = with_prefix is None and self._x4u_number_prefix()
        if prefix:
            return super()._get_last_sequence(relaxed=True, with_prefix=prefix)
        return super()._get_last_sequence(relaxed=relaxed, with_prefix=with_prefix)
