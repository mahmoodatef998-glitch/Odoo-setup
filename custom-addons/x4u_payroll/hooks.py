from odoo.addons.x4u_account.hooks import _account

SALARY_JOURNAL = ("SAL", "Salaries")
NET_PAYABLE = "201004"  # Accrued - Salaries: what the company owes the employees until the bank pays them.
ADVANCES = ("102016", "Staff Advances & Loans")

# rule xmlid: (debit code, credit code). Deductions are negative, so their "debit" account is credited.
RULE_ACCOUNTS = {
    "x4u_payroll.rule_basic": ("400003", None),
    "x4u_payroll.rule_housing": ("400004", None),
    "x4u_payroll.rule_transport": ("400005", None),
    "x4u_payroll.rule_other_allowance": ("400012", None),
    "x4u_payroll.rule_absence": ("400003", None),
    "x4u_payroll.rule_advance": ("102016", None),
    "x4u_payroll.rule_net": (None, NET_PAYABLE),
    "x4u_payroll.rule_eosb": ("400008", "202001"),
    "x4u_payroll.rule_leave_salary": ("400007", "201006"),
    "x4u_payroll.rule_air_ticket": ("400006", "201005"),
}


def post_init_hook(env):
    x4u_payroll_setup(env)


def x4u_payroll_setup(env):
    """Per company: the advances account, the Salaries journal, the rule accounts, contract defaults."""
    structure = env.ref("x4u_payroll.structure_uae")
    for company in env["res.company"].search([("chart_template", "!=", False)]):
        if not _account(env, company, ADVANCES[0]) and _account(env, company, NET_PAYABLE):
            env["account.account"].sudo().with_company(company).create(
                {"code": ADVANCES[0], "name": ADVANCES[1], "account_type": "asset_current"}
            )
        Journal = env["account.journal"].sudo()
        code, name = SALARY_JOURNAL
        journal = Journal.search([("code", "=", code), *Journal._check_company_domain(company)], limit=1)
        net = _account(env, company, NET_PAYABLE)
        if not journal and net:
            journal = Journal.create(
                {"name": name, "code": code, "type": "general", "company_id": company.id, "default_account_id": net.id}
            )
        if journal:
            Default = env["ir.default"].sudo()
            Default.set("hr.contract", "journal_id", journal.id, company_id=company.id)
            Default.set("hr.payslip.run", "journal_id", journal.id, company_id=company.id)
        env["ir.default"].sudo().set("hr.contract", "struct_id", structure.id, company_id=company.id)
        if company == env.ref("base.main_company", raise_if_not_found=False) or len(env.companies) == 1:
            for xmlid, (debit_code, credit_code) in RULE_ACCOUNTS.items():
                rule = env.ref(xmlid).sudo()
                values = {}
                debit = debit_code and _account(env, company, debit_code)
                credit = credit_code and _account(env, company, credit_code)
                if debit and not rule.account_debit:
                    values["account_debit"] = debit.id
                if credit and not rule.account_credit:
                    values["account_credit"] = credit.id
                if values:
                    rule.write(values)
