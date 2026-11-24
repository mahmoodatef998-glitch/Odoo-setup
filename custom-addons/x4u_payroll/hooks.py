from odoo.addons.x4u_account.hooks import _account

SALARY_JOURNAL = ("SAL", "Salaries")
# The Focus tree (x4u_account spec §19).
NET_PAYABLE = "215003"  # Accrued Salaries: what the company owes the employees until the bank pays them.
ADVANCES = ("136001", "Employee Advances")

# rule xmlid: (debit code, credit code). Deductions are negative, so their "debit" account is credited.
RULE_ACCOUNTS = {
    "x4u_payroll.rule_basic": ("510001", None),  # Salaries
    "x4u_payroll.rule_housing": ("530016", None),  # House Allowance
    "x4u_payroll.rule_transport": ("530015", None),  # Transportation Allowance
    "x4u_payroll.rule_other_allowance": ("530020", None),  # Salaries & Wages Other
    "x4u_payroll.rule_absence": ("510001", None),
    "x4u_payroll.rule_advance": ("136001", None),  # Employee Advances
    "x4u_payroll.rule_net": (None, NET_PAYABLE),
    "x4u_payroll.rule_eosb": ("530074", "215001"),  # End Of Service EXP / ACCRUED END OF SERVICE
    "x4u_payroll.rule_leave_salary": ("510002", "215002"),  # Leave Salary / ACCRUED LEAVE SALARY
    "x4u_payroll.rule_air_ticket": ("530079", "215005"),  # AIR TKT EXP / ACCRUED AIR TICKET
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
