import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Spec §13 L1: on this day of the month, Sales and Purchase lock up to the end of last month.
SOFT_LOCK_DAY_PARAM = "x4u_account.soft_lock_day"
SOFT_LOCK_DAY = 10
SOFT_LOCK_FIELDS = ("sale_lock_date", "purchase_lock_date")

# Next to "Post Dated Cheques Received" (102013) on the asset side; the account tree is
# still with the Accountant (docs/modules/06-accounting.md), so only the name is fixed.
PDC_ISSUED_CODE = "201020"


class ResCompany(models.Model):
    _inherit = "res.company"

    x4u_pdc_issued_account_id = fields.Many2one(
        "account.account",
        string="PDC Payable Account",
        help="Cheques given to vendors wait here until the bank clears them.",
    )

    x4u_overhead_applied_account_id = fields.Many2one(
        "account.account",
        string="Applied Overhead Account",
        help="The overhead added to a finished product (the MO's extra cost, e.g. the 20% of a generator) "
        "is credited here instead of Work In Progress.",
    )

    x4u_pdc_received_journal_id = fields.Many2one(
        "account.journal",
        string="PDC Received Journal",
        help="Customers' cheques wait here (Post Dated Cheques Received) until they are deposited at the bank.",
    )

    @api.model
    def _x4u_soft_lock_target(self, today):
        """The last day of the month that should be locked on `today`: on the 10th of November,
        31 October; on the 9th, still 30 September."""
        day = int(self.env["ir.config_parameter"].sudo().get_param(SOFT_LOCK_DAY_PARAM, SOFT_LOCK_DAY))
        return (today - relativedelta(days=day - 1)).replace(day=1) - relativedelta(days=1)

    @api.model
    def _x4u_cron_soft_lock(self, today=None):
        """Every day: no new or backdated invoice or bill in a month that is over (spec §13 L1).
        Only moves the lock dates forward; the Chief Accountant can move them back with Lock Dates."""
        target = self._x4u_soft_lock_target(today or fields.Date.context_today(self))
        for company in self.sudo().search([("chart_template", "!=", False)]):
            vals = {field: target for field in SOFT_LOCK_FIELDS if not company[field] or company[field] < target}
            if vals:
                company.write(vals)
                _logger.info("4U soft lock: %s locked up to %s for %s", ", ".join(vals), target, company.name)

    def _x4u_pdc_issued_account(self):
        """The company's PDC Payable account, created the first time it is needed."""
        self.ensure_one()
        if self.x4u_pdc_issued_account_id:
            return self.x4u_pdc_issued_account_id
        Account = self.env["account.account"].sudo().with_company(self)
        code = int(PDC_ISSUED_CODE)
        while Account.search_count([("code", "=", str(code)), *Account._check_company_domain(self)]):
            code += 1
        account = Account.create(
            {
                "code": str(code),
                "name": _("Post Dated Cheques Issued"),
                "account_type": "liability_current",
                "reconcile": True,
            }
        )
        self.sudo().x4u_pdc_issued_account_id = account
        return account
