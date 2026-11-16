from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_job_order.hooks import setup_engine_serials


def migrate(cr, version):
    """Spec v0.10 B4: genset bodies go by their serial. Bodies already in stock or delivered to the
    factory get a serial by a stock count; the open Job Orders that hold a body delivered without one
    reserve it again by its serial, so Finish Job Order does not stop ("Lot/Serial number is
    mandatory", like v0.8.1)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    jobs = env["mrp.production"].search([("x4u_is_job_order", "=", True), ("state", "not in", ("done", "cancel"))])
    bodies = env.ref("x4u_setup_base.categ_bodies", raise_if_not_found=False)
    if bodies:
        # The lines reserved without a serial go first: the count cannot take a reserved unit.
        stale = jobs.move_raw_ids.filtered(
            lambda m: m.state not in ("done", "cancel") and m.product_id.categ_id.parent_path.startswith(bodies.parent_path)
        ).move_line_ids.filtered(lambda line: not line.lot_id)
        moves = stale.move_id
        stale.unlink()
        moves.write({"picked": False})
    setup_engine_serials(env)
    jobs._x4u_reserve_delivered_parts(all_parts=True)
