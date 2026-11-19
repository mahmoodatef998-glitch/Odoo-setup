def migrate(cr, version):
    """v0.8 (the one PI of the order, the Salesperson's): the PI email changes. Odoo keeps noupdate
    records on upgrade, so the old email moves aside here, the module data creates the new one, and
    post-migrate drops the old one."""
    cr.execute(
        "UPDATE ir_model_data SET name = 'mail_template_proforma_v3' "
        "WHERE module = 'x4u_sale' AND name = 'mail_template_proforma'"
    )
