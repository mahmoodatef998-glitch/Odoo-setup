{
    "name": "4U Sales Payments",
    "summary": "Confirm when the customer agrees, then the customer PO (LPO); payment schedule from the terms "
    "or Custom; the Accountant checks the PO and issues one PI per order (S012-PI), payments on the PI, "
    "the tax invoice applies them",
    "version": "18.0.2.1.0",
    "category": "Sales/Sales",
    "license": "LGPL-3",
    "author": "4U Power Generation FZC",
    "depends": [
        "sale_management",
        "account",
        # The payment terms flagged "paid before delivery" (spec §6 S10).
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
