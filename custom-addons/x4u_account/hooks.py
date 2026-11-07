from odoo import Command

# Equity, after the Focus tree (Capital In Paid, Partner Paid, Reserves & Surplus, Profit/Loss).
# 999999 "Undistributed Profits/Losses" stays the current year's profit (spec §3). The codes
# are free in l10n_ae (no 3xxxxx); the Accountant may renumber them with the account tree.
EQUITY_ACCOUNTS = [
    ("301001", "Share Capital", "equity"),
    ("302001", "Partners' Current Accounts", "equity"),
    ("303001", "Statutory Reserve", "equity"),
    ("304001", "Retained Earnings", "equity"),
    ("305001", "Dividends / Profit Distribution", "equity"),
]

STATEMENT_SETTINGS = {"group_activity_statement": True, "group_outstanding_statement": True}

# Spec §8 Q1: the dirham is pegged to the dollar (Central Bank of the UAE, since 1997).
USD_PER_AED_PEG = 3.6725

# Spec §8 Q2: l10n_ae accounts with the wrong type (all without journal items on 2026-11-07).
ACCOUNT_FIXES = {
    # The VAT settlement accounts of the tax groups: owed to / by the FTA, not a customer or vendor.
    "100103": {"account_type": "asset_current", "reconcile": False},
    "202003": {"account_type": "liability_current", "reconcile": False},
    # 106xxx is the fixed assets group (spec §9): the assets, their depreciation, capital WIP.
    "106001": {"account_type": "asset_fixed"},
    "106002": {"account_type": "asset_fixed"},
    "106003": {"account_type": "asset_fixed"},
    "106004": {"account_type": "asset_fixed"},
    "106005": {"account_type": "asset_fixed"},
    "106006": {"account_type": "asset_fixed"},
    "106007": {"account_type": "asset_fixed"},
    "106008": {"account_type": "asset_fixed"},
    "106009": {"account_type": "asset_fixed"},
    "106010": {"account_type": "asset_non_current"},
}

# Spec §9: perpetual inventory. 103xxx is the inventory / shipments group of l10n_ae.
INVENTORY_ACCOUNTS = [
    ("103001", "Inventory - Generator Components", "asset_current", False),
    ("103002", "Inventory - Finished Generators", "asset_current", False),
    ("103003", "Inventory - Spare Parts", "asset_current", False),
    ("103004", "Work In Progress - Production", "asset_current", False),
    ("103005", "Goods Delivered Not Invoiced", "asset_current", True),
    ("201021", "Goods Received Not Invoiced", "liability_current", True),
    ("400072", "Applied Manufacturing Overhead", "expense", False),
]
INVENTORY_WRITE_OFF = "400036"

# Spec §11: fixed assets, straight-line, monthly, pro-rata. (name, asset, acc. depreciation, expense, years)
ASSET_JOURNAL = ("AST", "Fixed Assets")
ASSET_PROFILES = [
    ("Leasehold Improvements", "106001", "106006", "400063", 5),
    ("Furniture & Office Equipment", "106002", "106007", "400064", 5),
    ("Computer Hardware & Software", "106003", "106008", "400065", 3),
    ("Motor Vehicles", "106004", "106009", "400066", 5),
    # IFRS 16: each lease asset gets its own term; 5 years is only the default.
    ("Right-of-Use Assets (IFRS 16)", "100101", "100102", "400070", 5),
]

# Spec §10: landed costs. category xmlid: (clearing code, name). 103016-103018 exist in l10n_ae.
LANDED_COST_CATEGORIES = {
    "x4u_account.categ_landed_freight": ("103018", "Shipment Other Charges"),
    "x4u_account.categ_landed_insurance": ("103016", "Shipment Insurance"),
    "x4u_account.categ_landed_clearing": ("103017", "Shipments Documentation Charges"),
    "x4u_account.categ_landed_customs": ("103021", "Customs Duty Clearing"),
}
# category xmlid: inventory account code
VALUED_CATEGORIES = {
    "x4u_setup_base.categ_components": "103001",
    "x4u_setup_base.categ_engines": "103001",
    "x4u_setup_base.categ_alternators": "103001",
    "x4u_setup_base.categ_bodies": "103001",
    "x4u_setup_base.categ_generators": "103002",
    "x4u_setup_base.categ_spare_parts": "103003",
}
ACCOUNT_RENAMES = {"106005": ("Work In Progrees", "Work In Progress")}

# Spec §8 Q3: income / expense per product category (category xmlid: (income code, expense code)).
NEW_INCOME_ACCOUNTS = [("500015", "Spare Parts Sales", "income")]
CATEGORY_ACCOUNTS = {
    "x4u_setup_base.categ_generators": ("500001", "400001"),
    "x4u_setup_base.categ_components": ("500015", "400001"),
    "x4u_setup_base.categ_engines": ("500015", "400001"),
    "x4u_setup_base.categ_alternators": ("500015", "400001"),
    "x4u_setup_base.categ_bodies": ("500015", "400001"),
    "x4u_setup_base.categ_spare_parts": ("500015", "400001"),
    "x4u_setup_base.categ_services": ("500008", "400001"),
    # Rent, utilities...: an operating expense, not a cost of sales; each product can be more precise.
    "product.cat_expense": (None, "400050"),
}

MASS_RECONCILE_NAME = "4U: payments with invoices by reference"


def post_init_hook(env):
    x4u_setup(env)


def x4u_setup(env):
    """Everything per company, safe to run again (install and upgrades)."""
    for company in env["res.company"].search([("chart_template", "!=", False)]):
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
    env["res.config.settings"].create(STATEMENT_SETTINGS).execute()
    # The OCA job that posts the depreciation lines that are due (it ships inactive).
    cron = env.ref("account_asset_management.ir_cron_assets_generator", raise_if_not_found=False)
    if cron and not cron.active:
        cron.sudo().active = True


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
        company.x4u_overhead_applied_account_id = _account(env, company, "400072")
    grni = _account(env, company, "201021")
    gdni = _account(env, company, "103005")
    wip = _account(env, company, "103004")
    for xmlid, inventory_code in VALUED_CATEGORIES.items():
        category = env.ref(xmlid, raise_if_not_found=False)
        if not category:
            continue
        category = category.sudo().with_company(company)
        if category.property_valuation != "real_time":
            _switch_to_real_time(env, category, _account(env, company, inventory_code), wip, grni, gdni)
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


def _account(env, company, code):
    Account = env["account.account"].sudo().with_company(company)
    return Account.search([("code", "=", code), *Account._check_company_domain(company)], limit=1)


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
        if not _account(env, company, code) and _account(env, company, "500001"):
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
    }
    for xmlid, values in menus.items():
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu:
            menu.with_context(active_test=False).write(values)
