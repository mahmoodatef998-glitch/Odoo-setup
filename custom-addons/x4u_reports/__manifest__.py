# Copyright 2026 4U Power Generation FZC
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "4U Reports",
    "summary": "The 4U letterhead on every printed document: the header in English and Arabic with "
    "the logo and the contact line, the 4U watermark on every page, the brands at the bottom",
    "version": "18.0.1.0.0",
    "category": "Hidden",
    "license": "LGPL-3",
    "author": "4U Power Generation FZC",
    "depends": ["web"],
    "data": [
        "data/report_paperformat.xml",
        "views/report_layout_templates.xml",
        "views/res_company_views.xml",
    ],
    "assets": {
        "web.report_assets_common": ["x4u_reports/static/src/scss/x4u_letterhead.scss"],
    },
    "installable": True,
}
