from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_job_order.hooks import setup_engine_serials


def migrate(cr, version):
    """Spec v0.8: Job Order parts are free in stock (F1, F4) and engines go by serial (N1).

    The open Job Orders give back what Pick Components reserved for them, then the engines get
    their serials, then each Job Order's flag is worked out from the stock."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Production = env["mrp.production"]
    jobs = Production.search([("x4u_is_job_order", "=", True), ("x4u_job_state", "in", ("waiting_parts", "parts_ready"))])
    reserved = jobs._x4u_pick_components().move_ids.filtered(
        lambda move: move.state in ("assigned", "partially_available") and not move.picked
    )
    reserved._do_unreserve()
    setup_engine_serials(env)
    jobs._x4u_refresh_parts()
    env.add_to_compute(Production._fields["x4u_material_flag"], Production.search([("x4u_is_job_order", "=", True)]))
