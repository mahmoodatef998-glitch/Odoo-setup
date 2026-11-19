from collections import defaultdict

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Spec v0.12 J11: the Job Orders opened before (one per generator) go in one Job Order per sales
    order, named after its first one; their numbers and serials stay. The Serial tab shows what was
    delivered to each generator."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Job = env["x4u.job.order"]
    Production = env["mrp.production"].with_context(active_test=False)
    groups = defaultdict(lambda: Production.browse())
    for production in Production.search([("x4u_is_job_order", "=", True), ("x4u_job_id", "=", False)], order="id"):
        groups[production.x4u_sale_order_id or production] |= production
    for key, productions in groups.items():
        order = key if key._name == "sale.order" else env["sale.order"]
        job = Job.search([("sale_order_id", "=", order.id)], limit=1) if order else Job
        if not job:
            job = Job.create(
                {"name": productions[0].name, "sale_order_id": order.id or False, "company_id": productions[0].company_id.id}
            )
        productions.write({"x4u_job_id": job.id})
    for ready in env["x4u.ready.order"].search([("job_id", "=", False), ("sale_order_id", "!=", False)], order="id"):
        ready.job_id = Job._x4u_for_order(ready.sale_order_id)
    Serial = env["x4u.alternator.serial"]
    for production in Production.search([("x4u_is_job_order", "=", True)]):
        card = production.lot_producing_id.x4u_generator_id
        production.x4u_set_serials(
            x4u_engine_lot_id=card.x4u_engine_lot_id.id,
            x4u_body_lot_id=card.x4u_body_lot_id.id,
            x4u_alternator_id=Serial.search([("production_id", "=", production.id)], limit=1).id,
        )
