{
    "name": "4U Purchase Payments",
    "summary": "Payment terms and payment mode on the PO, Custom schedule, the vendor PI recorded and paid "
    "by the Accountant, advances linked to the PO, the vendor bill applies them",
    "version": "18.0.1.5.0",
    "category": "Inventory/Purchase",
    "license": "LGPL-3",
    "author": "4U Power Generation FZC",
    "depends": [
        "purchase",
        # UAT Phase 2: receipts (Delivery Note, the Accountant told) and the bill of a receipt.
        "purchase_stock",
        # The payment schedule, the payment linked to an order, the advances on the invoice.
        "x4u_sale",
    ],
    "data": [
        "security/x4u_purchase_security.xml",
        "security/ir.model.access.csv",
        "data/x4u_purchase_data.xml",
        "report/purchase_order_report.xml",
        "views/x4u_purchase_proforma_views.xml",
        "views/purchase_views.xml",
        "views/receipt_views.xml",
        "views/vendor_bill_views.xml",
    ],
    "assets": {
        # 2026-11-26: an empty or failed upload no longer leaves the attach button grey.
        "web.assets_backend": ["x4u_purchase/static/src/js/file_input_patch.esm.js"],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
}
