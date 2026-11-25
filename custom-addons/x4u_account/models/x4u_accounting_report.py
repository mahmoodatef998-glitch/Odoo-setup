from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class X4uAccountingReport(models.AbstractModel):
    """Spec §16 R3: the reports of Accounting › Reporting that open an OCA screen already set (the
    bank or cash accounts, customers and vendors, today). The screen is created here with its values:
    opening a new one would run the OCA onchanges, which empty the accounts. Everything stays editable
    before View, Export PDF or Export XLSX."""

    _name = "x4u.accounting.report"
    _description = "4U Accounting Reports"

    @api.model
    def _x4u_journal_accounts(self, journal_type):
        company = self.env.company
        Journal = self.env["account.journal"]
        journals = Journal.search([("type", "=", journal_type), *Journal._check_company_domain(company)])
        if journal_type == "bank":
            # Customers' cheques in hand are not the bank (spec §12).
            journals -= company.x4u_pdc_received_journal_id
        return journals.default_account_id

    @api.model
    def _x4u_open(self, model, values, title):
        wizard = self.env[model].create(values)
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": model,
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
        }

    @api.model
    def _x4u_ledger(self, accounts, title, **values):
        if not accounts:
            raise UserError(_("No account for %s: add the journals first (Configuration › Journals).", title))
        values = {"account_ids": [Command.set(accounts.ids)], "grouped_by": "none", "centralize": False, **values}
        return self._x4u_open("general.ledger.report.wizard", values, title)

    @api.model
    def action_x4u_bank_book(self):
        return self._x4u_ledger(self._x4u_journal_accounts("bank"), _("Bank Book"))

    @api.model
    def action_x4u_cash_book(self):
        return self._x4u_ledger(self._x4u_journal_accounts("cash"), _("Cash Book"))

    @api.model
    def _x4u_partner_accounts(self, types):
        Account = self.env["account.account"]
        return Account.search([("account_type", "in", types), *Account._check_company_domain(self.env.company)])

    @api.model
    def action_x4u_partner_ledger(self):
        accounts = self._x4u_partner_accounts(("asset_receivable", "liability_payable"))
        return self._x4u_ledger(
            accounts, _("Partner Ledger"), grouped_by="partners", receivable_accounts_only=True, payable_accounts_only=True
        )

    @api.model
    def action_x4u_customer_ledger(self):
        """Spec §22 G4: a partner that is customer and vendor is read one side at a time."""
        return self._x4u_ledger(
            self._x4u_partner_accounts(("asset_receivable",)), _("Customer Ledger"), grouped_by="partners",
            receivable_accounts_only=True,
        )

    @api.model
    def action_x4u_vendor_ledger(self):
        return self._x4u_ledger(
            self._x4u_partner_accounts(("liability_payable",)), _("Vendor Ledger"), grouped_by="partners",
            payable_accounts_only=True,
        )

    @api.model
    def action_x4u_day_book(self):
        today = fields.Date.context_today(self)
        Journal = self.env["account.journal"]
        journals = Journal.search(Journal._check_company_domain(self.env.company))
        values = {"date_from": today, "date_to": today, "journal_ids": [Command.set(journals.ids)]}
        return self._x4u_open("journal.ledger.report.wizard", values, _("Day Book"))

    @api.model
    def _x4u_open_items(self, account_type, title):
        values = {
            "account_ids": [Command.set(self._x4u_partner_accounts((account_type,)).ids)],
            "receivable_accounts_only": account_type == "asset_receivable",
            "payable_accounts_only": account_type == "liability_payable",
            "show_partner_details": True,
        }
        return self._x4u_open("open.items.report.wizard", values, title)

    @api.model
    def action_x4u_receivable_excel(self):
        return self._x4u_open_items("asset_receivable", _("Accounts Receivable (Excel)"))

    @api.model
    def action_x4u_payable_excel(self):
        return self._x4u_open_items("liability_payable", _("Accounts Payable (Excel)"))

    @api.model
    def _x4u_preview(self, instance):
        """The figures of a MIS report. OCA's report widget finds its report in the context
        (active_model / active_id), which Odoo only adds for a button on the report itself: a menu
        opens it through a server action, so they are added here (else "Invalid ids list")."""
        return instance.with_context(
            active_model="mis.report.instance", active_id=instance.id, active_ids=instance.ids
        ).preview()

    @api.model
    def action_x4u_monthly_pl(self):
        """Spec §17 M2: the P&L of this year, month by month (made the first time it is opened)."""
        from odoo.addons.x4u_account.hooks import _monthly_pl

        instance = _monthly_pl(self.env, self.env.company)
        if not instance:
            raise UserError(_("The 4U P&L report was removed: open MIS Reporting › MIS Reports."))
        return self._x4u_preview(instance)

    @api.model
    def _cron_x4u_monthly_pl(self):
        """M2: the new year's report is there from its first day."""
        from odoo.addons.x4u_account.hooks import _monthly_pl

        for company in self.env["res.company"].search([("chart_template", "!=", False)]):
            _monthly_pl(self.env, company)

    def action_x4u_mis(self, xmlid):
        """A 4U statement (MIS), straight to its figures: Print and Export are on top."""
        instance = self.env.ref(xmlid, raise_if_not_found=False)
        if not instance:
            raise UserError(_("This report was removed: open MIS Reporting › MIS Reports."))
        return self._x4u_preview(instance)
