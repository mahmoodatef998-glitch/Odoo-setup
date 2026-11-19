from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Spec v0.7 made a PI for each payment; v0.8 (18.0.2.3.0) is back to the one PI of the order,
    so an older database keeps its PIs as they are. The LPO to-dos of v0.6 are closed."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    lpo = env.ref("x4u_sale.mail_activity_type_lpo", raise_if_not_found=False)
    if lpo:
        env["mail.activity"].search([("activity_type_id", "=", lpo.id)]).unlink()
    old_template = env.ref("x4u_sale.mail_template_proforma_v2", raise_if_not_found=False)
    if old_template:
        old_template.unlink()
