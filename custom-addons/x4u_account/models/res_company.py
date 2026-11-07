from odoo import _, fields, models

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
