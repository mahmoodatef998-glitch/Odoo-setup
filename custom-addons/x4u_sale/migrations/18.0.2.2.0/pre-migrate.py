def migrate(cr, version):
    """Spec v0.7: "Waiting for LPO" is gone (the PO comes before the Confirm): those orders go to
    the Accountant (O10). The PI states are now Issued / Invoiced / Cancelled."""
    cr.execute("UPDATE sale_order SET x4u_po_check = 'to_check' WHERE x4u_po_check = 'waiting'")
    cr.execute("UPDATE x4u_sale_proforma SET state = 'issued' WHERE state IN ('open', 'paid')")
    # The PI email is noupdate data: its old text (Amount due now) goes, the new one is loaded.
    cr.execute(
        "UPDATE ir_model_data SET name = 'mail_template_proforma_v2' "
        "WHERE module = 'x4u_sale' AND name = 'mail_template_proforma'"
    )
