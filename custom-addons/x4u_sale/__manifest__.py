{
    "name": "4U Sales Payments",
    "summary": "Advance payments by proforma (S007-PF1), payments linked to the sales order, "
    "one tax invoice before delivery that applies the advances by itself",
    "version": "18.0.1.0.0",
    "category": "Sales/Sales",
    "license": "LGPL-3",
    "author": "4U Power Generation FZC",
    "depends": [
        "sale_management",
        "account",
        # The payment terms flagged "paid before delivery" (spec §6 B1).
        "x4u_setup_base",
    ],
    "data": [
        "security/x4u_sale_security.xml",
        "security/ir.model.access.csv",
        # The report before the data: the mail template attaches it.
        "report/x4u_sale_proforma_report.xml",
        "data/x4u_sale_data.xml",
        "views/x4u_sale_proforma_views.xml",
        "views/sale_account_views.xml",
    ],
    "installable": True,
}
