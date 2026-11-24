"""Every report of Accounting > Reporting for one company, and the checks that tie them together:
the Trial Balance balances, the General Ledger ends where it does, the partner reports agree with
the Customers / Suppliers accounts, the Tax Report with the tax lines, the P&L columns add up, the
Balance Sheet balances, the Cash Flow explains the bank. Changes nothing (rolled back).

    docker compose run --rm -T -e X4U_COMPANY="4U Power Generation FZC" -e X4U_DATE_TO=2026-11-30 \
        -v <folder>:/tmp/x4u_reports web odoo shell -d odoo4u_training --no-http < scripts/accounting_reports_check.py

The Excel files go to /tmp/x4u_reports when that folder is mounted.
"""

import json
import os
from datetime import date

name = os.environ.get("X4U_COMPANY") or env.ref("base.main_company").name
company = env["res.company"].search([("name", "=", name)], limit=1)
if not company:
    raise SystemExit("No company %r." % name)
env = env(context=dict(env.context, allowed_company_ids=company.ids, lang="en_US"))  # noqa: F821
company = company.with_env(env)
DATE_TO = os.environ.get("X4U_DATE_TO") or date.today().isoformat()
DATE_FROM = DATE_TO[:4] + "-01-01"
OUT = "/tmp/x4u_reports"
results = []
Report = env["ir.actions.report"]
Account = env["account.account"].with_company(company)


def save(report_name, records, data, filename):
    if not os.path.isdir(OUT):
        return 0
    content, _kind = Report._render_xlsx(report_name, records.ids, data)
    with open(os.path.join(OUT, filename), "wb") as handle:
        handle.write(content)
    return len(content)


def ok(title, good, detail):
    results.append(("OK  " if good else "FAIL") + " %-34s %s" % (title, detail))


def step(title, function):
    try:
        function()
    except Exception as exc:  # noqa: BLE001 - one broken report must not hide the others
        results.append("FAIL %-34s %s: %s" % (title, type(exc).__name__, str(exc)[:300]))


def wizard_data(model, values):
    wizard = env[model].create({"company_id": company.id, **values})
    return wizard, json.loads(json.dumps(wizard._prepare_report_data(), default=str))  # as the browser sends it


def balance(accounts, date_to=DATE_TO):
    lines = env["account.move.line"].search([("account_id", "in", accounts.ids), ("parent_state", "=", "posted"),
                                             ("date", "<=", date_to), ("company_id", "=", company.id)])
    return round(sum(lines.mapped("balance")), 2)


def num(v):
    return v if isinstance(v, (int, float)) else 0.0


def money(v):
    return "{:,.2f}".format(num(v))


state = {}
receivable = Account.search([("account_type", "=", "asset_receivable"), *Account._check_company_domain(company)])
payable = Account.search([("account_type", "=", "liability_payable"), *Account._check_company_domain(company)])


def trial_balance():
    wizard, data = wizard_data("trial.balance.report.wizard", {"date_from": DATE_FROM, "date_to": DATE_TO, "show_hierarchy": True,
                                                               "hide_account_at_0": True})
    tb = env["report.account_financial_report.trial_balance"]._get_report_values(wizard.ids, data)
    state["accounts"] = tb["accounts_data"]
    print("TRIAL BALANCE %s, %s - %s (by the account tree)" % (company.name, DATE_FROM, DATE_TO))
    for row in tb["trial_balance"]:
        if row["type"] == "group_type" and row["level"] <= 1:
            print("  %s%-5s %-26s opening %15s  period %15s  ending %15s" % ("  " * row["level"], row["code"], row["name"][:26],
                  money(row["initial_balance"]), money(row["balance"]), money(row["ending_balance"])))
    total = round(sum(a["ending_balance"] for a in tb["accounts_data"].values()), 2)
    ok("Trial Balance", abs(total) < 0.01, "%d accounts, debit = credit (sum %.2f), xlsx %d bytes"
       % (len(tb["accounts_data"]), total, save("a_f_r.report_trial_balance_xlsx", wizard, data, "Trial Balance.xlsx")))


def general_ledger():
    wizard, data = wizard_data("general.ledger.report.wizard", {"date_from": DATE_FROM, "date_to": DATE_TO})
    gl = env["report.account_financial_report.general_ledger"]._get_report_values(wizard.ids, data)
    accounts = state.get("accounts", {})
    wrong = [a["code"] for a in gl["general_ledger"]
             if a["id"] in accounts and abs(a["fin_bal"]["balance"] - accounts[a["id"]]["ending_balance"]) > 0.005]
    ok("General Ledger", not wrong, "%d accounts end where the Trial Balance does %s, xlsx %d bytes"
       % (len(gl["general_ledger"]), wrong or "", save("a_f_r.report_general_ledger_xlsx", wizard, data, "General Ledger.xlsx")))


def partner_ledger():
    wizard, data = wizard_data("general.ledger.report.wizard", {"date_from": DATE_FROM, "date_to": DATE_TO, "grouped_by": "partners",
                                                                "account_ids": [(6, 0, (receivable | payable).ids)]})
    pl = env["report.account_financial_report.general_ledger"]._get_report_values(wizard.ids, data)
    got = {a["id"]: round(a["fin_bal"]["balance"], 2) for a in pl["general_ledger"]}
    want = {a.id: balance(a) for a in receivable | payable}
    ok("Partner Ledger", all(abs(got.get(k, 0.0) - v) < 0.01 for k, v in want.items()),
       "customers %s, suppliers %s = their accounts, xlsx %d bytes"
       % (money(sum(got.get(a.id, 0.0) for a in receivable)), money(sum(got.get(a.id, 0.0) for a in payable)),
          save("a_f_r.report_general_ledger_xlsx", wizard, data, "Partner Ledger.xlsx")))


def partner_reports():
    for model, report, title in (("aged.partner.balance.report.wizard", "aged_partner_balance", "Aged Partner Balance"),
                                 ("open.items.report.wizard", "open_items", "Open Items")):
        for side, accounts in (("customers", receivable), ("suppliers", payable)):
            def run(model=model, report=report, title=title, side=side, accounts=accounts):
                wizard, data = wizard_data(model, {"date_at": DATE_TO, "account_ids": [(6, 0, accounts.ids)]})
                values = env["report.account_financial_report.%s" % report]._get_report_values(wizard.ids, data)
                detail = ""
                if report == "aged_partner_balance":
                    rows = values["aged_partner_balance"]
                    amount = round(sum(a["residual"] for a in rows), 2)
                    keys = ("current", "30_days", "60_days", "90_days", "120_days", "older")
                    detail = " | ".join("%s %s" % (k, "{:,.0f}".format(sum(a.get(k, 0.0) for a in rows))) for k in keys)
                else:
                    amount = 0.0
                    for total in values["total_amount"].values():
                        amount += total["residual"] if "residual" in total else sum(
                            p.get("residual", 0.0) for p in total.values() if isinstance(p, dict))
                    amount = round(amount, 2)
                want = balance(accounts)
                xlsx = save("a_f_r.report_%s_xlsx" % report, wizard, data, "%s - %s.xlsx" % (title, side))
                ok("%s %s" % (title, side), abs(amount - want) < 0.01, "%s = account %s, xlsx %d bytes %s"
                   % (money(amount), money(want), xlsx, detail))
            step("%s %s" % (title, side), run)


def journals():
    wizard, data = wizard_data("journal.ledger.report.wizard", {"date_from": DATE_TO[:8] + "01", "date_to": DATE_TO,
                               "journal_ids": [(6, 0, env["account.journal"].search([("company_id", "=", company.id)]).ids)]})
    jl = env["report.account_financial_report.journal_ledger"]._get_report_values(wizard.ids, data)
    debit = round(sum(j["debit"] for j in jl["Journal_Ledgers"]), 2)
    credit = round(sum(j["credit"] for j in jl["Journal_Ledgers"]), 2)
    ok("Day Book / Journals (month)", debit == credit, "%d entries, debit %s = credit %s, xlsx %d bytes"
       % (sum(len(j["report_moves"]) for j in jl["Journal_Ledgers"]), money(debit), money(credit),
          save("a_f_r.report_journal_ledger_xlsx", wizard, data, "Journals.xlsx")))


def vat():
    wizard, data = wizard_data("vat.report.wizard", {"date_from": DATE_FROM, "date_to": DATE_TO, "tax_detail": True})
    values = env["report.account_financial_report.vat_report"]._get_report_values(wizard.ids, data)
    taxes = env["account.tax"].search([("company_id", "=", company.id)])
    tax_lines = env["account.move.line"].search([("tax_line_id", "in", taxes.ids), ("parent_state", "=", "posted"),
                                                 ("date", ">=", DATE_FROM), ("date", "<=", DATE_TO)])
    sale = -sum(tax_lines.filtered(lambda l: l.tax_line_id.type_tax_use == "sale").mapped("balance"))
    purchase = sum(tax_lines.filtered(lambda l: l.tax_line_id.type_tax_use == "purchase").mapped("balance"))
    # The UAE return boxes: each has a (Base) and a (Tax) line; the (Tax) lines are the VAT.
    boxes = [row for row in values["vat_report"] if row.get("name", "").endswith("(Tax)")]
    out_tax = -sum(num(row.get("tax")) for row in boxes if num(row.get("tax")) < 0)
    in_tax = sum(num(row.get("tax")) for row in boxes if num(row.get("tax")) > 0)
    ok("Tax Report", abs(out_tax - sale) < 0.01 and abs(in_tax - purchase) < 0.01,
       "output VAT %s, input VAT %s, payable to the FTA %s (%s), xlsx %d bytes"
       % (money(out_tax), money(in_tax), money(out_tax - in_tax), ", ".join(row["name"] for row in boxes),
          save("a_f_r.report_vat_report_xlsx", wizard, data, "Tax Report.xlsx")))


def matrix_rows(instance):
    matrix = instance._compute_matrix()
    return {row.kpi.name: [getattr(c, "val", None) if c else None for c in row.iter_cells()]
            for row in matrix.iter_rows() if not getattr(row, "account_id", None)}


def export(instance, title):
    if os.path.isdir(OUT):
        content, _kind = Report._render_xlsx("mis_builder.mis_report_instance_xlsx", instance.ids, {})
        with open(os.path.join(OUT, "%s.xlsx" % title), "wb") as handle:
            handle.write(content)


def mis(xmlid, title, check):
    """A statement of Generic Statements, opened like the menu does, for the selected company."""
    instance = env.ref(xmlid)
    env["x4u.accounting.report"].action_x4u_mis(xmlid)
    good, detail = check(matrix_rows(instance))
    export(instance, title)
    ok(title, good and not instance.company_id, "%s (columns: %s)%s"
       % (detail, ", ".join(instance.period_ids.sorted("sequence").mapped("name")),
          "" if not instance.company_id else " - FIXED ON %s" % instance.company_id.name))


def pl_check(rows):
    missing = [round(num(v), 2) for v in rows.get("not_in_report", [])]
    return all(abs(m) < 0.01 for m in missing), "net profit %s, accounts not in the report %s" % (
        [money(v) for v in rows.get("net_profit", [])], missing)


def cash_flow_check(rows):
    checks = [round(num(v), 2) for v in rows.get("check", [])]
    return all(abs(c) < 0.01 for c in checks), "check %s, cash at the end %s" % (checks, [money(v) for v in rows.get("cash_end", [])])


def bs_check(rows):
    pairs = list(zip(rows.get("assets", []), rows.get("liability_header", [])))
    return bool(pairs) and all(abs(num(a) - num(b)) < 0.01 for a, b in pairs), "assets = liabilities + equity: %s, profit %s" % (
        [(money(a), money(b)) for a, b in pairs], [money(v) for v in rows.get("current_ue", [])])


def monthly():
    from odoo.addons.x4u_account.hooks import _monthly_pl

    instance = _monthly_pl(env, company, date.fromisoformat(DATE_TO))
    rows = matrix_rows(instance)
    months = [num(v) for v in rows.get("net_profit", [])]
    good = len(months) > 1 and abs(sum(months[:-1]) - months[-1]) < 0.01
    export(instance, "Monthly Profit and Loss")
    ok("Monthly Profit and Loss", good, "%s: the months add up to the Total %s" % (instance.name, money(months[-1] if months else 0)))


step("Trial Balance", trial_balance)
step("General Ledger", general_ledger)
step("Partner Ledger", partner_ledger)
partner_reports()
step("Day Book / Journals (month)", journals)
step("Tax Report", vat)
step("Profit and Loss", lambda: mis("x4u_account.mis_instance_x4u_pl", "Profit and Loss", pl_check))
step("Monthly Profit and Loss", monthly)
step("Balance Sheet", lambda: mis("x4u_account.mis_instance_x4u_bs", "Balance Sheet", bs_check))
step("Cash Flow Statement", lambda: mis("x4u_account.mis_instance_x4u_cash_flow", "Cash Flow Statement", cash_flow_check))
step("Cash & Working Capital", lambda: mis("x4u_account.mis_instance_x4u_cash", "Cash and Working Capital", lambda rows: (True, "runs")))
print("REPORTS-BEGIN %s" % company.name)
for line in results:
    print(line)
print("REPORTS-END")
env.cr.rollback()
