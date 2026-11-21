# Copyright 2026 4U Power Generation FZC
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "4U Theme",
    "summary": "The 4U look: black navbar with the company logo and a yellow line, yellow main "
    "buttons, readable dark-gold links, a branded login page, and a Home page with the user's apps as cards",
    "version": "18.0.1.1.0",
    "category": "Hidden",
    "license": "LGPL-3",
    "author": "4U Power Generation FZC",
    "depends": ["web"],
    "data": [
        "views/res_company_views.xml",
        "views/login_templates.xml",
        "data/home_action.xml",
    ],
    "assets": {
        # Before Odoo's own !default values, so the whole UI takes the 4U colors.
        "web._assets_primary_variables": [
            ("prepend", "x4u_theme/static/src/scss/primary_variables.scss"),
        ],
        "web.assets_backend": [
            "x4u_theme/static/src/scss/backend.scss",
            "x4u_theme/static/src/webclient/navbar.xml",
            "x4u_theme/static/src/home/home.js",
            "x4u_theme/static/src/home/home.xml",
            "x4u_theme/static/src/home/home.scss",
        ],
        "web.assets_frontend": [
            "x4u_theme/static/src/scss/login.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
}
