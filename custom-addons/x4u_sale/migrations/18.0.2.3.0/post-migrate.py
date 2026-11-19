from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """v0.8 Q6 / Q10: the PIs made for each payment stay, with the new statuses."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    old = env.ref("x4u_sale.mail_template_proforma_v3", raise_if_not_found=False)
    if old:
        old.unlink()
    proformas = env["x4u.sale.proforma"].search([])
    env.add_to_compute(proformas._fields["state"], proformas)
    proformas.flush_recordset()
