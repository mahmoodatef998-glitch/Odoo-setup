{
    "name": "4U Setup - 4U Power Generation",
    "summary": "4U-only setup: numbering, 2-step manufacturing, routes, "
    "pricelists, sales team, quotation template, service products",
    "version": "18.0.1.0.1",
    "category": "Hidden",
    "license": "LGPL-3",
    "author": "4U Power Generation FZC",
    "depends": [
        "x4u_setup_base",
        "sale_mrp",
    ],
    "data": [
        "data/pricelist_data.xml",
        "data/product_data.xml",
        "data/sale_order_template_data.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
