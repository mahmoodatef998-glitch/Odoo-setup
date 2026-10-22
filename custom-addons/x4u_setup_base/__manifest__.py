{
    "name": "4U Setup - Base",
    "summary": "Shared 4U / ATA setup: settings, categories, units, "
    "generator attributes, CRM stages, payment terms, document numbering, "
    "purchase approval to-do",
    "version": "18.0.1.0.3",
    "category": "Hidden",
    "license": "LGPL-3",
    "author": "4U Power Generation FZC",
    "depends": [
        "account",
        "sale_management",
        "sale_crm",
        "purchase_stock",
        "mrp",
    ],
    "data": [
        "data/product_category_data.xml",
        "data/uom_data.xml",
        "data/product_attribute_data.xml",
        "data/crm_stage_data.xml",
        "data/crm_lost_reason_data.xml",
        "data/payment_term_data.xml",
        "data/mail_activity_type_data.xml",
        "views/res_company_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
