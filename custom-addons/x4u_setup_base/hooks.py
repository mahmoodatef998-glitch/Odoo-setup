# Settings shared by 4U and ATA (docs/specs/x4u_setup_sales.md §5). Applied
# once at install through the Settings logic, so Odoo's own side effects
# (implied groups, company fields) happen exactly as if done by hand.
SETTINGS = {
    "group_uom": True,
    "group_product_variant": True,
    "group_product_pricelist": True,
    "group_discount_per_so_line": True,
    "group_sale_order_template": True,
    "group_sale_delivery_address": True,
    "group_proforma_sales": True,
    "group_stock_production_lot": True,
    "group_stock_multi_locations": True,
    "group_stock_adv_location": True,
    # Every purchase order waits for the General Manager (blueprint C10).
    "po_order_approval": True,
    "po_double_validation_amount": 0.0,
}
# Added 2026-10-21 (docs/modules/01-sales.md §4: D9, D10, S4).
SETTINGS_V2 = {
    "group_auto_done_setting": True,  # confirmed sales orders are locked
    "account_use_credit_limit": True,  # credit limit per customer
    "lead_enrich_auto": "manual",  # nothing sent to Odoo's IAP servers by itself
}

# Odoo defaults we don't use (D11). Ours are in data/.
UNUSED_PAYMENT_TERMS = (
    "account.account_payment_term_15days",
    "account.account_payment_term_21days",
    "account.account_payment_term_45days",
    "account.account_payment_term_end_following_month",
    "account.account_payment_term_30_days_end_month_the_10",
    "account.account_payment_term_advance_60days",
    "account.account_payment_term_30days_early_discount",
    "account.account_payment_term_90days_on_the_10th",
)
UNUSED_LOST_REASONS = ("crm.lost_reason_1", "crm.lost_reason_2", "crm.lost_reason_3")


def apply_settings(env, settings):
    Settings = env["res.config.settings"]
    # Skip a setting whose app isn't installed (e.g. lead enrichment).
    Settings.create({key: value for key, value in settings.items() if key in Settings._fields}).execute()


def archive_unused_defaults(env):
    for xmlid in UNUSED_PAYMENT_TERMS + UNUSED_LOST_REASONS:
        record = env.ref(xmlid, raise_if_not_found=False)
        if record:
            record.active = False


def post_init_hook(env):
    env.ref("base.USD").active = True
    apply_settings(env, {**SETTINGS, **SETTINGS_V2})
    archive_unused_defaults(env)
