import calendar
import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import Command, fields

from .focus_chart import ACCOUNTS as FOCUS_ACCOUNTS
from .focus_chart import CODE
from .focus_chart import GROUPS as FOCUS_GROUPS
from .focus_chart import OLD_CODES
from .focus_chart import PL_GROUPS

_logger = logging.getLogger(__name__)

# Equity in the Focus tree, OWNERSHIP (spec §19); 900002 "Profit/Loss A/C" is the profit not yet
# distributed (Odoo's current year earnings).
EQUITY_ACCOUNTS = [
    ("240006", "Capital In Paid", "equity"),
    ("240005", "Current Account", "equity"),
    ("240007", "Reserves & Surplus", "equity"),
    ("240008", "Retained Earnings", "equity"),
    ("230003", "DIVIDENDS", "equity"),
]

STATEMENT_SETTINGS = {"group_activity_statement": True, "group_outstanding_statement": True}
# Spec §20 P3: the serial of every unit printed on the delivery slip.
SERIAL_SETTINGS = {"group_lot_on_delivery_slip": True}

# Spec §20 P1 (UAT 2026-11-24): every stock item at the average of what was paid for it (AVCO);
# an item valued per serial (engine, CKD, body, generator) keeps its own cost, and its product
# shows the average of the serials in stock.
COST_METHOD = "average"

# Spec §8 Q1: the dirham is pegged to the dollar (Central Bank of the UAE, since 1997).
USD_PER_AED_PEG = 3.6725

# Spec §8 Q2: l10n_ae accounts with the wrong type, fixed while they have no journal items
# (by their Focus codes, spec §19).
ACCOUNT_FIXES = {
    # The VAT settlement accounts of the tax groups: owed to / by the FTA, not a customer or vendor.
    CODE["vat_refundable"]: {"account_type": "asset_current", "reconcile": False},
    CODE["fta"]: {"account_type": "liability_current", "reconcile": False},
    # 14xxxx is the fixed assets group (spec §9): the assets, their depreciation, capital WIP.
    "140007": {"account_type": "asset_fixed"},
    "140004": {"account_type": "asset_fixed"},
    "140003": {"account_type": "asset_fixed"},
    "140001": {"account_type": "asset_fixed"},
    "140008": {"account_type": "asset_fixed"},
    "140097": {"account_type": "asset_fixed"},
    "140094": {"account_type": "asset_fixed"},
    "140093": {"account_type": "asset_fixed"},
    "140091": {"account_type": "asset_fixed"},
    "140010": {"account_type": "asset_non_current"},
}

# Spec §9: perpetual inventory, in the Focus INVENTORY group 134 (spec §19).
INVENTORY_ACCOUNTS = [
    (CODE["inventory_components"], "Stock - Raw Material", "asset_current", False),
    (CODE["inventory_generators"], "Stock - Finished Goods", "asset_current", False),
    (CODE["inventory_spare_parts"], "Stock - Spare Parts", "asset_current", False),
    (CODE["wip"], "Work In Progress", "asset_current", False),
    (CODE["gdni"], "Goods Delivered Not Invoiced", "asset_current", True),
    (CODE["grni"], "Goods Received Not Invoiced", "liability_current", True),
    (CODE["overhead_applied"], "Overhead Applied (to generators)", "expense", False),
]
INVENTORY_WRITE_OFF = CODE["inventory_write_off"]

# Spec §11: fixed assets, straight-line, monthly, pro-rata. (name, asset, acc. depreciation, expense, years)
# One depreciation expense, "Depreciation :EXP", as in the Focus tree.
ASSET_JOURNAL = ("AST", "Fixed Assets")
ASSET_PROFILES = [
    ("Leasehold Improvements", "140007", "140097", CODE["depreciation"], 5),
    ("Furniture & Office Equipment", "140004", "140094", CODE["depreciation"], 5),
    ("Computer Hardware & Software", "140003", "140093", CODE["depreciation"], 3),
    ("Motor Vehicles", "140001", "140091", CODE["depreciation"], 5),
    ("Machinery & Tools", "140002", "140092", CODE["depreciation"], 5),
    # IFRS 16: each lease asset gets its own term; 5 years is only the default.
    ("Right-of-Use Assets (IFRS 16)", "140009", "140098", CODE["depreciation"], 5),
]

# Spec §10: landed costs. category xmlid: (clearing code, name), in the INVENTORY group.
LANDED_COST_CATEGORIES = {
    "x4u_account.categ_landed_freight": (CODE["landed_other"], "Shipment Other Charges"),
    "x4u_account.categ_landed_insurance": (CODE["landed_insurance"], "Shipment Insurance"),
    "x4u_account.categ_landed_clearing": (CODE["landed_documents"], "Shipments Documentation Charges"),
    "x4u_account.categ_landed_customs": (CODE["landed_customs"], "Customs Duty Clearing"),
}
# category xmlid: inventory account code
VALUED_CATEGORIES = {
    "x4u_setup_base.categ_components": CODE["inventory_components"],
    "x4u_setup_base.categ_engines": CODE["inventory_components"],
    "x4u_setup_base.categ_alternators": CODE["inventory_components"],
    "x4u_setup_base.categ_bodies": CODE["inventory_components"],
    # x4u_job_order spec v0.9 C1: an engine + alternator on one serial, a part like the engine.
    "x4u_setup_base.categ_ckd": CODE["inventory_components"],
    "x4u_setup_base.categ_generators": CODE["inventory_generators"],
    "x4u_setup_base.categ_spare_parts": CODE["inventory_spare_parts"],
}
ACCOUNT_RENAMES = {}

# Spec §8 Q3: income / expense per product category (category xmlid: (income code, expense code)).
NEW_INCOME_ACCOUNTS = [(CODE["sales_spare_parts"], "Sales Spare Parts", "income")]
CATEGORY_ACCOUNTS = {
    "x4u_setup_base.categ_generators": (CODE["sales_generators"], CODE["cost_of_sales"]),
    "x4u_setup_base.categ_components": (CODE["sales_spare_parts"], CODE["cost_of_sales"]),
    "x4u_setup_base.categ_engines": (CODE["sales_spare_parts"], CODE["cost_of_sales"]),
    "x4u_setup_base.categ_alternators": (CODE["sales_spare_parts"], CODE["cost_of_sales"]),
    "x4u_setup_base.categ_bodies": (CODE["sales_spare_parts"], CODE["cost_of_sales"]),
    "x4u_setup_base.categ_ckd": (CODE["sales_spare_parts"], CODE["cost_of_sales"]),
    "x4u_setup_base.categ_spare_parts": (CODE["sales_spare_parts"], CODE["cost_of_sales"]),
    "x4u_setup_base.categ_services": (CODE["sales_services"], CODE["cost_of_sales"]),
    # Rent, utilities...: an operating expense, not a cost of sales; each product can be more precise.
    "product.cat_expense": (None, CODE["other_expenses"]),
}

MASS_RECONCILE_NAME = "4U: payments with invoices by reference"

# Spec §12: customers' post-dated cheques wait in PDCR (132001) until they are deposited.
PDC_RECEIVED_ACCOUNT = (CODE["pdc_received"], "PDCR - Post Dated Cheques Received")
# After the real bank journals (sequence 10), so Odoo never proposes it as "the" bank.
PDC_RECEIVED_JOURNAL = ("CHK", "PDC Received", 90)


def post_init_hook(env):
    x4u_setup(env)
    x4u_direct_bank(env)


def x4u_setup(env):
    """Everything per company, safe to run again (install and upgrades). Each company in its own
    context: company-dependent values (a category's accounts, an account's asset profile) land on
    that company, not on the first one (spec §19: 4U and ATA)."""
    main_env = env
    for company in main_env["res.company"].search([("chart_template", "!=", False)]):
        env = main_env(context=dict(main_env.context, allowed_company_ids=company.ids))
        company = company.with_env(env)
        _focus_chart(env, company)
        _pl_groups(env, company)
        _advance_accounts(env, company)
        company._x4u_pdc_issued_account()
        _equity_accounts(env, company)
        _petty_cash(env, company)
        _mass_reconcile(env, company)
        _bank_auto_reconcile(env, company)
        _usd_peg(env, company)
        _fix_accounts(env, company)
        _category_accounts(env, company)
        _perpetual_inventory(env, company)
        _landed_costs(env, company)
        _asset_profiles(env, company)
        _pdc_received(env, company)
        _fiscal_years(env, company)
        _budget_report(env, company)
        _monthly_pl(env, company)
        _gbp_rate_provider(env, company)
        _focus_chart_cleanup(env, company)
    env = main_env
    _statements_follow_the_company(env)
    _trn_label(env)
    _aging_config(env)
    env["res.config.settings"].create(STATEMENT_SETTINGS).execute()
    env["res.config.settings"].create(SERIAL_SETTINGS).execute()
    # The OCA job that posts the depreciation lines that are due (it ships inactive).
    cron = env.ref("account_asset_management.ir_cron_assets_generator", raise_if_not_found=False)
    if cron and not cron.active:
        cron.sudo().active = True


AGING_NAME = "4U: 0-30 / 31-60 / 61-90 / +90 days (from the invoice date)"
# The accounting team, 2026-11-27. An amount dated today shows under Current.
AGING_INTERVALS = (("0-30 days", 30), ("31-60 days", 60), ("61-90 days", 90), ("+90 days", 100000))


def _aging_config(env):
    """The Aged Partner Balance of each company opens in 0-30 / 31-60 / 61-90 / +90 days, aged from
    the invoice date (the accounting team, 2026-11-27)."""
    Config = env["account.age.report.configuration"].sudo()
    for company in env["res.company"].sudo().search([]):
        config = Config.search([("company_id", "=", company.id), ("x4u_default", "=", True)], limit=1)
        if config:
            continue
        Config.with_company(company).create(
            {
                "name": AGING_NAME,
                "company_id": company.id,
                "x4u_from_invoice_date": True,
                "x4u_default": True,
                "line_ids": [Command.create({"name": name, "inferior_limit": limit}) for name, limit in AGING_INTERVALS],
            }
        )


def _trn_label(env):
    """Spec §21 V3: the UAE tax number is called TRN on the tax invoice and bill (Odoo prints the
    label of the company's country, and the UAE has none, so it said "Tax ID")."""
    uae = env.ref("base.ae")
    if uae.vat_label != "TRN":
        uae.vat_label = "TRN"


def _pdc_received(env, company):
    """Spec §12 K1: the PDC Received journal. A customer's cheque is a payment in this journal; it
    waits in 102013 until a Check Deposit moves it to the bank's Outstanding Receipts."""
    code, name = PDC_RECEIVED_ACCOUNT
    account = _account(env, company, code) or env["account.account"].sudo().with_company(company).create(
        {"code": code, "name": name, "account_type": "asset_current"}
    )
    # The deposit reconciles each cheque out of it, so the balance is the cheques in hand.
    if not account.reconcile:
        account.reconcile = True
    company = company.sudo()
    journal = company.x4u_pdc_received_journal_id
    if not journal:
        Journal = env["account.journal"].sudo()
        journal_code, journal_name, sequence = PDC_RECEIVED_JOURNAL
        journal = Journal.search([("code", "=", journal_code), *Journal._check_company_domain(company)], limit=1)
        if not journal:
            # Its cheques wait in PDC Received: not one of the journals paid straight to the bank.
            journal = Journal.with_context(x4u_no_direct_payments=True).create(
                {"name": journal_name, "code": journal_code, "type": "bank", "sequence": sequence, "company_id": company.id}
            )
        company.x4u_pdc_received_journal_id = journal
    manual = journal.inbound_payment_method_line_ids.filtered(lambda line: line.code == "manual")[:1]
    if manual and not manual.payment_account_id:
        manual.payment_account_id = account
    # Cheques in hand are not paid out: only the deposit takes them out.
    if not env["account.payment"].sudo().search_count([("journal_id", "=", journal.id), ("payment_type", "=", "outbound")]):
        journal.outbound_payment_method_line_ids.unlink()


BUDGET_REPORT_NAME = "4U P&L vs Budget"
MONTHLY_PL_NAME = "4U Monthly P&L %s"


def _monthly_pl(env, company, day=None):
    """Spec §17 M1: the 4U P&L of the fiscal year that has `day` (today), a column per month and its
    total. Made once per year; the Accountant may change its columns."""
    report = env.ref("x4u_account.mis_report_x4u_pl", raise_if_not_found=False)
    if not report:
        return env["mis.report.instance"]
    day = day or fields.Date.context_today(company)
    dates = company.compute_fiscalyear_dates(day)
    start, end = dates["date_from"], dates["date_to"]
    name = MONTHLY_PL_NAME % (end.year if start.year == end.year else "%s-%s" % (start.year, end.year))
    Instance = env["mis.report.instance"].sudo()
    instance = Instance.search([("name", "=", name), ("company_id", "in", (company.id, False))], limit=1)
    if instance:
        return instance
    periods = []
    month = start
    sequence = 10
    while month <= end:
        last = min(month + relativedelta(months=1, days=-1), end)
        periods.append(
            Command.create(
                {
                    "name": month.strftime("%b %Y"),
                    "sequence": sequence,
                    "mode": "fix",
                    "manual_date_from": month,
                    "manual_date_to": last,
                }
            )
        )
        month += relativedelta(months=1)
        sequence += 10
    periods.append(
        Command.create(
            {"name": "Total", "sequence": sequence, "mode": "fix", "manual_date_from": start, "manual_date_to": end}
        )
    )
    return Instance.create(
        {
            "name": name,
            "report_id": report.id,
            "company_id": company.id,
            "comparison_mode": True,
            "display_columns_description": True,
            "period_ids": periods,
        }
    )


def _budget_report(env, company):
    """Spec §16 R2: a budget by account for this fiscal year (the Accountant fills its lines from
    Reporting › Management › Budgets), and the 4U P&L vs Budget on it: Actual, Budget and Variance,
    year to date."""
    report = env.ref("x4u_account.mis_report_x4u_pl", raise_if_not_found=False)
    if not report:
        return
    today = fields.Date.context_today(company)
    dates = company.compute_fiscalyear_dates(today)
    Budget = env["mis.budget.by.account"].sudo()
    budget = Budget.search(
        [("company_id", "=", company.id), ("date_from", "<=", today), ("date_to", ">=", today)], limit=1
    ) or Budget.create(
        {
            "name": "Budget %s" % dates["date_to"].year,
            "date_from": dates["date_from"],
            "date_to": dates["date_to"],
            "company_id": company.id,
        }
    )
    Instance = env["mis.report.instance"].sudo()
    if Instance.search_count([("name", "=", BUDGET_REPORT_NAME), ("company_id", "in", (company.id, False))]):
        return
    ytd = {"mode": "relative", "type": "m", "offset": 0, "is_ytd": True}
    instance = Instance.create(
        {
            "name": BUDGET_REPORT_NAME,
            "report_id": report.id,
            "company_id": company.id,
            "comparison_mode": True,
            "display_columns_description": True,
            "period_ids": [
                Command.create({"name": "Actual (Year to Date)", "sequence": 10, **ytd}),
                Command.create(
                    {
                        "name": "Budget (Year to Date)",
                        "sequence": 20,
                        "source": "mis_budget_by_account",
                        "source_mis_budget_by_account_id": budget.id,
                        **ytd,
                    }
                ),
            ],
        }
    )
    actual, planned = instance.period_ids.sorted("sequence")
    instance.write(
        {
            "period_ids": [
                Command.create(
                    {
                        "name": "Variance",
                        "sequence": 30,
                        # A compare column has no dates of its own.
                        "mode": "none",
                        "source": "cmpcol",
                        "source_cmpcol_from_id": planned.id,
                        "source_cmpcol_to_id": actual.id,
                    }
                )
            ]
        }
    )


def _fiscal_years(env, company):
    """Spec §13 L3: this fiscal year and the next one (January-December by default; the company's
    Fiscal Year Last Day decides). OCA account_fiscal_year_auto_create adds the following ones."""
    FiscalYear = env["account.fiscal.year"].sudo()
    last_month = int(company.fiscalyear_last_month)
    today = fields.Date.context_today(company)
    for year in (today.year, today.year + 1):
        last_day = min(company.fiscalyear_last_day, calendar.monthrange(year, last_month)[1])
        date_to = date(year, last_month, last_day)
        date_from = date_to - relativedelta(years=1) + relativedelta(days=1)
        if FiscalYear.search_count(
            [("company_id", "=", company.id), ("date_from", "<=", date_to), ("date_to", ">=", date_from)]
        ):
            continue
        name = "FY %s" % year if date_from.year == year else "FY %s-%s" % (date_from.year, year)
        FiscalYear.create({"name": name, "company_id": company.id, "date_from": date_from, "date_to": date_to})


def _asset_profiles(env, company):
    """One profile per asset class; each asset account points to its profile, so a vendor bill
    line on 106002 (furniture...) creates the asset by itself (spec §11)."""
    Journal = env["account.journal"].sudo()
    code, name = ASSET_JOURNAL
    journal = Journal.search([("code", "=", code), *Journal._check_company_domain(company)], limit=1)
    if not journal:
        journal = Journal.create({"name": name, "code": code, "type": "general", "company_id": company.id})
    Profile = env["account.asset.profile"].sudo()
    for profile_name, asset_code, depreciation_code, expense_code, years in ASSET_PROFILES:
        asset, depreciation, expense = (_account(env, company, c) for c in (asset_code, depreciation_code, expense_code))
        if not (asset and depreciation and expense):
            continue
        profile = Profile.search([("name", "=", profile_name), ("company_id", "=", company.id)], limit=1)
        if not profile:
            profile = Profile.create(
                {
                    "name": profile_name,
                    "company_id": company.id,
                    "account_asset_id": asset.id,
                    "account_depreciation_id": depreciation.id,
                    "account_expense_depreciation_id": expense.id,
                    "journal_id": journal.id,
                    "method": "linear",
                    "method_time": "year",
                    "method_number": years,
                    "method_period": "month",
                    "prorata": True,
                }
            )
        asset = asset.with_company(company)
        if not asset.asset_profile_id:
            asset.asset_profile_id = profile


def _landed_costs(env, company):
    """The forwarder's bill debits the clearing account; the validated landed cost credits it into
    the inventory value, so the clearing account closes at zero (spec §10)."""
    Account = env["account.account"].sudo().with_company(company)
    Category = env["product.category"].sudo().with_company(company)
    fallback = Category._fields["property_account_expense_categ_id"].get_company_dependent_fallback(Category)
    input_fallback = Category._fields["property_stock_account_input_categ_id"].get_company_dependent_fallback(Category)
    for xmlid, (code, name) in LANDED_COST_CATEGORIES.items():
        category = env.ref(xmlid, raise_if_not_found=False)
        if not category:
            continue
        clearing = _account(env, company, code) or Account.create(
            {"code": code, "name": name, "account_type": "asset_current"}
        )
        # Odoo matches each bill line with its landed cost on this account (one shipment at a time).
        if not clearing.reconcile:
            clearing.reconcile = True
        category = category.sudo().with_company(company)
        if category.property_account_expense_categ_id == fallback:
            category.property_account_expense_categ_id = clearing
        if category.property_stock_account_input_categ_id == input_fallback:
            category.property_stock_account_input_categ_id = clearing


def _switch_to_real_time(env, category, inventory, wip, grni, gdni):
    """Periodic to perpetual for one category (spec §9 S1).

    During the switch, input and output are the category's expense account: the stock on hand
    comes in as Dr Inventory / Cr Cost of Goods Sold (its parts were expensed there). Odoo refuses
    the switch while products valued per serial have history (the generators, x4u_job_order V6),
    so their serial valuation is turned off for the switch and back on after; that round trip
    posts out / in on the same accounts, so it nets to zero."""
    expense = category.property_account_expense_categ_id
    category.write(
        {
            "property_stock_valuation_account_id": inventory.id,
            "property_stock_account_production_cost_id": wip.id,
            "property_stock_account_input_categ_id": expense.id,
            "property_stock_account_output_categ_id": expense.id,
        }
    )
    templates = (
        env["product.template"]
        .sudo()
        .with_context(active_test=False)
        .search([("categ_id", "=", category.id), ("lot_valuated", "=", True)])
        .filtered(lambda t: t.product_variant_ids.stock_valuation_layer_ids)
    )
    if templates:
        templates.write({"lot_valuated": False})
    category.property_valuation = "real_time"
    if templates:
        templates.write({"lot_valuated": True})
    category.write({"property_stock_account_input_categ_id": grni.id, "property_stock_account_output_categ_id": gdni.id})


def _perpetual_inventory(env, company):
    """Spec §9: automated valuation + Anglo-Saxon on the valued categories, once per category.

    The stock already on hand comes in against the category's expense account (its parts were
    expensed there under periodic valuation): Dr Inventory / Cr Cost of Goods Sold."""
    Account = env["account.account"].sudo().with_company(company)
    for code, name, account_type, reconcile in INVENTORY_ACCOUNTS:
        if not _account(env, company, code):
            Account.create({"code": code, "name": name, "account_type": account_type, "reconcile": reconcile})
    company = company.sudo()
    if not company.anglo_saxon_accounting:
        company.anglo_saxon_accounting = True
    if not company.x4u_overhead_applied_account_id:
        company.x4u_overhead_applied_account_id = _account(env, company, CODE["overhead_applied"])
    grni = _account(env, company, CODE["grni"])
    gdni = _account(env, company, CODE["gdni"])
    wip = _account(env, company, CODE["wip"])
    for xmlid, inventory_code in VALUED_CATEGORIES.items():
        category = env.ref(xmlid, raise_if_not_found=False)
        if not category:
            continue
        category = category.sudo().with_company(company)
        if category.property_valuation != "real_time":
            _switch_to_real_time(env, category, _account(env, company, inventory_code), wip, grni, gdni)
        _average_cost(env, category)
        _cogs_at_delivery(category)
    _gdni_to_cogs(env, company)
    write_off = _account(env, company, INVENTORY_WRITE_OFF)
    if write_off:
        Location = env["stock.location"].sudo().with_context(active_test=False)
        for location in Location.search([("usage", "=", "inventory"), ("company_id", "in", (company.id, False))]):
            location.write(
                {
                    "valuation_in_account_id": location.valuation_in_account_id.id or write_off.id,
                    "valuation_out_account_id": location.valuation_out_account_id.id or write_off.id,
                }
            )


def _average_cost(env, category):
    """Spec §20 P1: the category at the average cost. Without stock it is Odoo's own change.

    With stock, Odoo would empty and refill it (and refuses to when products are valued per serial):
    from FIFO to average nothing has to be re-valued, the stock keeps the value it has. So only the
    method changes, and each serial and product cost is set to its value / quantity in stock, which
    is what the average method takes for the next issue. No journal entry: the value is unchanged."""
    from odoo.models import BaseModel

    if category.property_cost_method == COST_METHOD:
        return
    products = (
        env["product.product"].sudo().with_company(category.env.company).with_context(active_test=False)
        .search([("categ_id", "=", category.id), ("is_storable", "=", True)])
    )
    # Odoo also refuses when a serial-valued product only has history (all of it issued).
    if not products.stock_valuation_layer_ids:
        category.property_cost_method = COST_METHOD
        return
    in_stock = products.filtered(lambda product: product.quantity_svl)
    BaseModel.write(category, {"property_cost_method": COST_METHOD})
    currency = category.env.company.currency_id
    for product in in_stock:
        if product.lot_valuated:
            lots = env["stock.lot"].sudo().with_company(category.env.company).search([("product_id", "=", product.id)])
            for lot in lots.filtered(lambda lot: lot.quantity_svl):
                BaseModel.write(lot, {"standard_price": currency.round(lot.value_svl / lot.quantity_svl)})
        BaseModel.write(product, {"standard_price": currency.round(product.value_svl / product.quantity_svl)})
    _logger.info("x4u_account: %s at the average cost, %s products in stock kept at their value", category.display_name, len(in_stock))


def _cogs_at_delivery(category):
    """Spec §20 P2 (UAT 2026-11-24): the cost of sales when the goods leave, Dr Cost of Sales /
    Cr Inventory, not with the invoice: the stock output account is the category's cost of sales."""
    expense = category.property_account_expense_categ_id
    if expense and category.property_stock_account_output_categ_id != expense:
        category.property_stock_account_output_categ_id = expense


def _gdni_to_cogs(env, company):
    """Spec §20 P2: what was left in Goods Delivered Not Invoiced when the cost of sales moved to the
    delivery goes to the cost of sales, per product and sales line (with its analytic). Delivered,
    not invoiced: the cost of sales now. Invoiced, not delivered: the invoice's cost of sales comes
    back, the delivery posts it."""
    gdni = _account(env, company, CODE["gdni"])
    if not gdni:
        return
    Line = env["account.move.line"].sudo()
    lines = Line.search(
        [("account_id", "=", gdni.id), ("parent_state", "=", "posted"), ("company_id", "=", company.id), ("reconciled", "=", False)]
    )
    groups = {}
    for line in lines:
        sale_line = (
            line.move_id.stock_move_id.sale_line_id or line.cogs_origin_id.sale_line_ids[:1] or line.x4u_cogs_sale_line_id
        )
        groups.setdefault((line.product_id, sale_line), Line)
        groups[(line.product_id, sale_line)] |= line
    for (product, sale_line), group in groups.items():
        balance = company.currency_id.round(sum(group.mapped("amount_residual")))
        expense = product.product_tmpl_id.with_company(company).get_product_accounts()["expense"] if product else False
        if company.currency_id.is_zero(balance) or not expense or expense == gdni:
            if company.currency_id.is_zero(balance) and len(group) > 1:
                group.reconcile()
            continue
        label = "GDNI to cost of sales (cost of sales at delivery) - %s" % (product.display_name,)
        common = {"name": label, "product_id": product.id, "partner_id": group.partner_id[:1].id}
        move = env["account.move"].sudo().create(
            {
                "move_type": "entry",
                "journal_id": product.categ_id.with_company(company).property_stock_journal.id
                or env["account.journal"].sudo().search([("type", "=", "general"), ("company_id", "=", company.id)], limit=1).id,
                "company_id": company.id,
                "ref": label,
                "line_ids": [
                    Command.create(dict(common, account_id=expense.id, balance=balance,
                                        analytic_distribution=sale_line.analytic_distribution or False)),
                    Command.create(dict(common, account_id=gdni.id, balance=-balance, x4u_cogs_sale_line_id=sale_line.id or False)),
                ],
            }
        )
        move.action_post()
        (group | move.line_ids.filtered(lambda aml: aml.account_id == gdni)).reconcile()
        _logger.info("x4u_account: GDNI %s of %s moved to the cost of sales (%s)", balance, product.display_name, move.name)


def _account(env, company, code):
    Account = env["account.account"].sudo().with_company(company)
    return Account.search([("code", "=", code), *Account._check_company_domain(company)], limit=1)


def _focus_chart(env, company):
    """Spec §19: the Focus account tree. Each l10n_ae account the tree replaces takes its Focus code
    and name (its entries, journals and settings stay); the missing accounts are made; the groups are
    the tree. An account that already has its Focus code is the Accountant's: left as it is."""
    Account = env["account.account"].sudo().with_company(company)
    domain = Account._check_company_domain(company)
    by_code = {a.code: a for a in Account.search(domain)}
    names = {code: (name, account_type, reconcile) for code, name, account_type, reconcile in FOCUS_ACCOUNTS}
    Line = env["account.move.line"].sudo()
    for old, new in OLD_CODES.items():
        account = by_code.get(old)
        if not account:
            continue
        used = Line.search_count([("account_id", "=", account.id)], limit=1)
        if new in by_code:
            # Several l10n_ae accounts are one Focus account: an empty one hands its settings over and
            # goes; one with entries keeps its code (the cleanup moves it to the 99 group).
            if not used:
                _repoint_account(env, company, account, by_code[new])
                try:
                    with env.cr.savepoint():
                        account.unlink()
                    by_code.pop(old)
                except Exception:  # noqa: BLE001 - still needed somewhere: the cleanup keeps it in 99
                    _logger.info("Focus chart: %s kept next to %s", old, new)
            continue
        name, account_type, reconcile = names[new]
        values = {"code": new, "name": name}
        if not used:
            values.update({"account_type": account_type, "reconcile": reconcile})
        account.write(values)
        by_code[new] = by_code.pop(old)
    for code, (name, account_type, reconcile) in names.items():
        if code not in by_code:
            by_code[code] = Account.create({"code": code, "name": name, "account_type": account_type, "reconcile": reconcile})
    Group = env["account.group"].sudo().with_company(company)
    groups = {g.code_prefix_start: g for g in Group.search([("company_id", "=", company.id)])}
    for prefix, name in FOCUS_GROUPS:
        values = {"name": name, "code_prefix_start": prefix, "code_prefix_end": prefix, "company_id": company.id}
        if prefix in groups:
            groups[prefix].write(values)
        else:
            Group.create(values)


def _pl_groups(env, company):
    """The accounting team, 2026-11-27: the P&L group (O / S / G / X) of each Focus expense account,
    on the accounts that have none yet (the Accountant's choice on an account stays)."""
    Account = env["account.account"].sudo().with_company(company)
    for account in Account.search([*Account._check_company_domain(company), ("x4u_pl_group", "=", False)]):
        group = PL_GROUPS.get(account.code)
        if group:
            account.x4u_pl_group = group


def _advance_accounts(env, company):
    """The accounting team, 2026-11-27: 216001 takes the customers' advances, 137012 the vendors'
    (unless the Accountant chose other accounts)."""
    for kind, code in (("customer", CODE["customer_advances"]), ("vendor", CODE["vendor_advances"])):
        Account = env["account.account"].sudo().with_company(company)
        if Account.search_count([*Account._check_company_domain(company), ("x4u_partner_advance", "=", kind)], limit=1):
            continue
        account = _account(env, company, code)
        if account:
            account.x4u_partner_advance = kind


def x4u_direct_bank(env):
    """The accounting team, 2026-11-27: payments straight to the bank. Each bank and cash journal's
    payment methods post to the journal's account, and what is still on Outstanding Receipts /
    Payments goes to the bank (cash) of its payment. On install and once on upgrade (18.0.1.16.0): a
    method the Accountant sets back to an outstanding account later stays so."""
    main_env = env
    for company in main_env["res.company"].search([("chart_template", "!=", False)]):
        env = main_env(context=dict(main_env.context, allowed_company_ids=company.ids))
        company = company.with_env(env)
        Journal = env["account.journal"].sudo()
        Journal.search([*Journal._check_company_domain(company), ("type", "in", ("bank", "cash"))])._x4u_direct_payment_accounts()
        _outstanding_to_bank(env, company)


def _outstanding_to_bank(env, company):
    """Each payment still open on Outstanding Receipts / Payments: Dr Bank / Cr Outstanding (or the
    other way), on the payment's date (the first open day if that is locked), matched."""
    outstanding = _account(env, company, CODE["outstanding_receipts"]) | _account(env, company, CODE["outstanding_payments"])
    if not outstanding:
        return
    lines = env["account.move.line"].sudo().search(
        [
            ("company_id", "=", company.id),
            ("account_id", "in", outstanding.ids),
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("payment_id", "!=", False),
        ],
        order="date, id",
    )
    for line in lines:
        payment = line.payment_id
        journal = payment.journal_id
        bank = journal.default_account_id
        if not bank or bank in outstanding:
            continue
        lock = company._get_user_fiscal_lock_date(journal)
        day = line.date if line.date > lock else lock + relativedelta(days=1)
        label = "%s: %s" % (payment.name, line.account_id.name)
        move = env["account.move"].sudo().create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "date": day,
                "ref": "Straight to the bank - %s" % payment.name,
                "line_ids": [
                    Command.create(
                        {
                            "name": label,
                            "account_id": line.account_id.id,
                            "partner_id": line.partner_id.id,
                            "currency_id": line.currency_id.id,
                            "amount_currency": -line.amount_residual_currency,
                            "balance": -line.amount_residual,
                        }
                    ),
                    Command.create(
                        {
                            "name": label,
                            "account_id": bank.id,
                            "partner_id": line.partner_id.id,
                            "currency_id": line.currency_id.id,
                            "amount_currency": line.amount_residual_currency,
                            "balance": line.amount_residual,
                        }
                    ),
                ],
            }
        )
        move.action_post()
        (line + move.line_ids.filtered(lambda new: new.account_id == line.account_id)).reconcile()
        _logger.info("Straight to the bank: %s moved to %s (%s)", payment.name, bank.code, move.name)


def _account_fields(env):
    """Every stored field that points to an account (model name, field name, type)."""
    for model_name in env.registry:
        Model = env[model_name]
        if Model._transient or Model._abstract or not Model._auto or model_name == "account.account":
            continue
        for field_name, field in Model._fields.items():
            if field.type in ("many2one", "many2many") and field.comodel_name == "account.account" and field.store:
                yield model_name, field_name, field.type


def _repoint_account(env, company, old, new):
    """What points to `old` (a setting, a category, a profile, a tax line...) points to `new`."""
    for model_name, field_name, field_type in _account_fields(env):
        Model = env[model_name].sudo().with_company(company).with_context(active_test=False)
        try:
            records = Model.search([(field_name, "in", old.ids)])
        except Exception:  # noqa: BLE001 - not searchable: nothing to move
            continue
        if not records:
            continue
        if field_type == "many2one":
            records.write({field_name: new.id})
        else:
            records.write({field_name: [Command.unlink(old.id), Command.link(new.id)]})
    for default in env["ir.default"].sudo().search([("field_id.relation", "=", "account.account")]):
        if default.json_value and default.json_value.strip('"') == str(old.id):
            default.json_value = str(new.id)


def _account_ids_in_use(env, company, ids):
    """The accounts of `ids` that any record or setting points to (a deleted account would leave a
    setting empty: the company's exchange accounts, a category's income account...)."""
    used = set()
    for model_name, field_name, _field_type in _account_fields(env):
        Model = env[model_name].sudo().with_company(company).with_context(active_test=False)
        try:
            records = Model.search([(field_name, "in", list(ids))])
            used |= set(records.mapped(field_name).ids) & set(ids)
        except Exception:  # noqa: BLE001 - a field that cannot be searched counts as "in use"
            _logger.info("Focus chart: %s.%s not searchable, its accounts are kept", model_name, field_name)
            return set(ids)
    for default in env["ir.default"].sudo().search([("field_id.relation", "=", "account.account")]):
        value = default.json_value and default.json_value.strip('"')
        if value and value.isdigit() and int(value) in ids:
            used.add(int(value))
    return used


def _focus_chart_cleanup(env, company):
    """Spec §19: the l10n_ae accounts outside the tree that nothing uses go; the ones still used
    (journal items, a journal, a tax, a setting) stay, in the group 99 "Odoo System Accounts"."""
    Account = env["account.account"].sudo().with_company(company)
    focus_codes = {code for code, *_rest in FOCUS_ACCOUNTS}
    template_ids = set(
        env["ir.model.data"].sudo().search([("model", "=", "account.account"), ("module", "=", "account")]).mapped("res_id")
    )
    candidates = Account.search(
        [*Account._check_company_domain(company), ("id", "in", list(template_ids)), ("code", "not in", list(focus_codes))]
    ).filtered(lambda a: not a.code.startswith("990"))
    if not candidates:
        return
    used = _account_ids_in_use(env, company, set(candidates.ids))
    taken = set(Account.search(Account._check_company_domain(company)).mapped("code"))
    number = 1
    for account in candidates:
        if account.id not in used and not env["account.move.line"].sudo().search_count([("account_id", "=", account.id)], limit=1):
            try:
                with env.cr.savepoint():
                    account.unlink()
                continue
            except Exception:  # noqa: BLE001 - still needed somewhere: kept below
                _logger.info("Focus chart: %s %s kept", account.code, account.name)
        while "99%04d" % number in taken:
            number += 1
        taken.add("99%04d" % number)
        account.code = "99%04d" % number


def _statements_follow_the_company(env):
    """The statements of Accounting › Reporting show the company selected at the top, not the one
    that installed the module (spec §19: 4U and ATA, the same tree)."""
    for xmlid in ("mis_instance_x4u_pl", "mis_instance_x4u_pl_6m", "mis_instance_x4u_cash",
                  "mis_instance_x4u_cash_flow", "mis_instance_x4u_bs"):
        instance = env.ref("x4u_account.%s" % xmlid, raise_if_not_found=False)
        if instance and instance.company_id and not instance.multi_company:
            instance.sudo().company_id = False
    # The balance sheet at a date: the balances then and the profit since the start of the year,
    # not the profit of that one day or month (it would not balance).
    for xmlid in ("mis_instance_x4u_bs_today", "mis_instance_x4u_bs_last_month"):
        period = env.ref("x4u_account.%s" % xmlid, raise_if_not_found=False)
        if period and not period.is_ytd:
            period.sudo().is_ytd = True


def _usd_peg(env, company):
    """One USD rate at the peg, valid for every date, unless someone already set rates."""
    usd = env.ref("base.USD")
    if company.currency_id != env.ref("base.AED") or company.currency_id == usd:
        return
    Rate = env["res.currency.rate"].sudo()
    if not Rate.search_count([("currency_id", "=", usd.id), ("company_id", "in", (company.id, False))]):
        if not usd.active:
            usd.sudo().active = True
        Rate.create(
            {
                "currency_id": usd.id,
                "company_id": company.id,
                "name": "1997-11-01",
                "rate": 1 / USD_PER_AED_PEG,
            }
        )


def _gbp_rate_provider(env, company):
    """Spec §18: GBP every day from the ECB through the USD peg; made once, the Accountant may change it."""
    if company.currency_id != env.ref("base.AED"):
        return
    service = "X4U_ECB_USD_PEG"
    Provider = env["res.currency.rate.provider"].sudo().with_context(active_test=False)
    if Provider.search_count([("service", "=", service), ("company_id", "=", company.id)]):
        return
    gbp = env.ref("base.GBP")
    if not gbp.active:
        gbp.sudo().active = True
    Provider.create({"service": service, "company_id": company.id, "currency_ids": [Command.set(gbp.ids)]})


def _fix_accounts(env, company):
    for code, values in ACCOUNT_FIXES.items():
        account = _account(env, company, code)
        if account and not env["account.move.line"].sudo().search_count([("account_id", "=", account.id)]):
            account.write(values)
    for code, (old, new) in ACCOUNT_RENAMES.items():
        account = _account(env, company, code)
        if account and account.with_context(lang="en_US").name == old:
            account.name = new


def _category_accounts(env, company):
    """Only where the category still uses the company default, so the Accountant's choices stay."""
    Account = env["account.account"].sudo().with_company(company)
    for code, name, account_type in NEW_INCOME_ACCOUNTS:
        if not _account(env, company, code) and _account(env, company, CODE["sales_generators"]):
            Account.create({"code": code, "name": name, "account_type": account_type})
    Category = env["product.category"].sudo().with_company(company)
    default_income = Category._fields["property_account_income_categ_id"].get_company_dependent_fallback(Category)
    default_expense = Category._fields["property_account_expense_categ_id"].get_company_dependent_fallback(Category)
    for xmlid, (income_code, expense_code) in CATEGORY_ACCOUNTS.items():
        category = env.ref(xmlid, raise_if_not_found=False)
        if not category:
            continue
        category = category.sudo().with_company(company)
        income = income_code and _account(env, company, income_code)
        expense = expense_code and _account(env, company, expense_code)
        if income and category.property_account_income_categ_id == default_income:
            category.property_account_income_categ_id = income
        if expense and category.property_account_expense_categ_id == default_expense:
            category.property_account_expense_categ_id = expense


def _equity_accounts(env, company):
    Account = env["account.account"].sudo().with_company(company)
    for code, name, account_type in EQUITY_ACCOUNTS:
        if not Account.search_count([("code", "=", code), *Account._check_company_domain(company)]):
            Account.create({"code": code, "name": name, "account_type": account_type})


def _petty_cash(env, company):
    """Cash journals are petty cash at 4U: the journal and its account say so (spec §2)."""
    Journal = env["account.journal"].sudo()
    for journal in Journal.search([("type", "=", "cash"), *Journal._check_company_domain(company)]):
        if journal.with_context(lang="en_US").name == "Cash":
            journal.name = "Petty Cash"
        account = journal.default_account_id
        if account and account.with_context(lang="en_US").name == "Cash":
            account.name = "Petty Cash"


def _receivable_payable_accounts(company):
    partner = company.partner_id.with_company(company)
    return partner.property_account_receivable_id | partner.property_account_payable_id


def _mass_reconcile(env, company):
    """Every night: a payment meets its invoice when the partner and the reference are the same,
    and the amounts settle to zero (no write-off). Anything else stays for the Accountant (spec §4 R2)."""
    MassReconcile = env["account.mass.reconcile"].sudo()
    for account in _receivable_payable_accounts(company):
        if MassReconcile.search_count([("account_id", "=", account.id), ("company_id", "=", company.id)]):
            continue
        MassReconcile.create(
            {
                "name": "%s (%s)" % (MASS_RECONCILE_NAME, account.code),
                "account_id": account.id,
                "company_id": company.id,
                "reconcile_method": [Command.create({"name": "mass.reconcile.advanced.ref", "write_off": 0.0})],
            }
        )


def _bank_auto_reconcile(env, company):
    """Bank statement lines: only the perfect match (partner + reference + exact amount) is automatic."""
    Model = env["account.reconcile.model"].sudo()
    for model in Model.search([("rule_type", "=", "invoice_matching"), ("company_id", "=", company.id)]):
        perfect = model.allow_payment_tolerance and not model.payment_tolerance_param and model.match_partner
        if perfect and model.match_text_location_label and not model.auto_reconcile:
            model.auto_reconcile = True


def uninstall_hook(env):
    """Put Odoo's own menus back the way they were."""
    menus = {
        "account.product_product_menu_sellable": {"active": True},
        "account.product_product_menu_purchasable": {"active": True},
        "account.menu_action_move_in_invoice_type": {"name": "Bills"},
        "account_asset_management.menu_finance_assets": {
            "parent_id": env.ref("account.menu_finance").id,
            "sequence": 9,
        },
        "account.menu_action_account_moves_all": {
            "groups_id": [Command.set(env.ref("account.group_account_readonly").ids)],
        },
        "account_usability.menu_accounting_statement_cash": {"name": "Cash Registers"},
        "account_due_list.menu_action_invoice_payments": {
            "parent_id": env.ref("account.menu_finance_entries").id,
            "sequence": 50,
        },
        "account_check_deposit.menu_check_deposit_tree": {"name": "Checks Deposits"},
        "account_lock_date_update.account_update_lock_date_menu": {"groups_id": [Command.clear()]},
    }
    for xmlid, values in menus.items():
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu:
            menu.with_context(active_test=False).write(values)
