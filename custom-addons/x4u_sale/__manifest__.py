{
    "name": "4U Sales Payments",
    "summary": "The Salesperson makes the one PI of the order (S012-PI) and sends the customer PO and "
    "the first payment receipt, the Accountant checks them, records the payment on the PI and confirms; "
    "payment schedule from the terms or Custom; the tax invoice applies the payments",
    "version": "18.0.2.3.0",
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
