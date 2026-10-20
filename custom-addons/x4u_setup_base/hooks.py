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


def post_init_hook(env):
    env.ref("base.USD").active = True
    env["res.config.settings"].create(SETTINGS).execute()
