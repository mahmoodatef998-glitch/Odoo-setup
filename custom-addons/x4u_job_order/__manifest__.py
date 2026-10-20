# Copyright 2026 4U Power Generation FZC
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "4U Job Orders",
    "summary": "Generator Job Orders: status, parts tracking, material "
    "requests, timeline of every step and where the delay is",
    "version": "18.0.1.0.0",
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
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/x4u_job_order_security.xml",
        "data/ir_cron.xml",
        "views/mrp_production_views.xml",
        "views/other_views.xml",
    ],
    "installable": True,
}
