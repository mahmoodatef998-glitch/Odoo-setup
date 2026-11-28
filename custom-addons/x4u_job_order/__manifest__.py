# Copyright 2026 4U Power Generation FZC
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "4U Job Orders",
    "summary": "Generator Job Orders: status, parts tracking, material "
    "requests, timeline of every step and where the delay is",
    "version": "18.0.1.27.0",
    "category": "Manufacturing/Manufacturing",
    # AGPL-3 because it depends on x4u_generator (AGPL-3).
    "license": "AGPL-3",
    "author": "4U Power Generation FZC",
    "depends": [
        "x4u_setup_4u",
        "x4u_generator",
        "sale_mrp",
        "purchase_mrp",
        "purchase_request",
        # The generator value: parts consumed + overhead (spec v0.4 V5).
        "mrp_account",
        # The final invoice to-do and the delivery after payment (x4u_sale spec §6 B9 / B10).
        "x4u_sale",
    ],
    "data": [
        # The group first: the access rules below use it.
        "security/x4u_job_order_security.xml",
        "security/ir.model.access.csv",
        "data/ir_config_parameter_data.xml",
        "data/ir_cron.xml",
        # Profitability per Job Order (spec v0.5 A1-A3).
        "data/analytic_data.xml",
        "data/x4u_ready_order_data.xml",
        # x4u_generator_datasheet §5: the 2026 price lists (Export AED, Perkins in GBP).
        "data/x4u_catalog_pricelist_data.xml",
        "views/x4u_job_profitability_views.xml",
        "views/x4u_job_order_deliver_views.xml",
        "views/x4u_ready_order_views.xml",
        "views/x4u_ready_receipt_views.xml",
        "views/x4u_alternator_serial_views.xml",
        # Spec v0.12: the order's one Job Order; its action is on the menus of the next file.
        "views/x4u_job_order_views.xml",
        "views/mrp_production_views.xml",
        "views/other_views.xml",
        # Spec v0.11 D3: the generator serials on the delivery note, the invoice and the sales order.
        "report/x4u_generator_serials_templates.xml",
        # Spec v0.14 H2-H4: the order's profitability, each generator by its serials.
        "report/x4u_cost_sheet_templates.xml",
        # x4u_generator_datasheet §9: the 4U quotation (QT 1112 layout).
        "report/x4u_quotation_templates.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
