# Copyright 2026 4U Power Generation FZC
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "4U Generator Card",
    "summary": "Generator card per serial: kVA, engine/alternator, "
    "running hours, warranty, sales and quality links",
    "version": "18.0.1.0.1",
    "category": "Inventory/Inventory",
    # AGPL-3 because it depends on quality_control_stock_oca (AGPL-3), see spec Q1.
    "license": "AGPL-3",
    "author": "4U Power Generation FZC",
    "depends": [
        "stock",
        "sale_stock",
        "quality_control_stock_oca",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/x4u_generator_security.xml",
        "data/ir_cron.xml",
        "views/x4u_generator_brand_views.xml",
        "views/x4u_generator_views.xml",
        "views/product_template_views.xml",
        "views/stock_lot_views.xml",
        "views/sale_order_views.xml",
        "views/res_partner_views.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/x4u_generator_demo.xml",
    ],
    "installable": True,
    "application": False,
}
