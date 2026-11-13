# Copyright 2026 4U Power Generation FZC
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "4U Accounting",
    "summary": "Accounting the 4U way: menus, PDC cheques to vendors, equity accounts, Petty Cash, "
    "Receivables & Payables (due lists, aging, statements) and safe automatic reconciliation",
    "version": "18.0.1.6.1",
    "category": "Accounting/Accounting",
    # AGPL-3 because it depends on account_asset_management (AGPL-3).
    "license": "AGPL-3",
    "author": "4U Power Generation FZC",
    "depends": [
        "account",
        # Its Assets menu moves under Accounting › Accounting.
        "account_asset_management",
        # Bank and Cash › Petty Cash.
        "account_usability",
        # Bank statement lines reconcile by themselves on a perfect match (spec §4 R1).
        "account_reconcile_oca",
        # Nightly matching of payments with invoices by reference (spec §4 R2).
        "account_mass_reconcile",
        # Receivables & Payables (spec §5).
        "account_due_list",
        "account_due_list_days_overdue",
        "account_financial_report",
        "partner_statement",
        # Perpetual inventory: WIP and the applied overhead of a finished product (spec §9).
        "mrp_account",
        # The cost of sales of a line invoiced before it is delivered (spec §9 S6).
        "sale_stock",
        # The categories it values.
        "x4u_setup_base",
        # Freight, insurance, clearing and customs in the inventory value (spec §10).
        "stock_landed_costs",
        # Phase 5: customers' PDC deposited at the bank (spec §12).
        "account_check_deposit",
        # Monthly closing: the Chief Accountant's Lock Dates, fiscal years (spec §13).
        "account_lock_date_update",
        "account_fiscal_year_auto_create",
        # Management reports (spec §14); the OCA Balance Sheet template and its styles.
        "mis_template_financial_report",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/account_payment_method_data.xml",
        "data/landed_cost_data.xml",
        "data/landed_cost_product_data.xml",
        "data/ir_cron_data.xml",
        "data/mis_report_data.xml",
        "data/mis_report_instance_data.xml",
        "views/account_payment_views.xml",
        "wizard/x4u_pdc_bounce_views.xml",
        "views/receivable_payable_views.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "installable": True,
}
