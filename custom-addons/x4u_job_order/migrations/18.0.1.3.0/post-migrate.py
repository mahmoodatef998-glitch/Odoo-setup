"""Spec v0.4 (2026-10-27): FIFO costing for generators and their parts, no inspection
after production, and the stage days recomputed without the QC stage."""
from odoo import SUPERUSER_ID, api

from odoo.addons.x4u_job_order.hooks import set_costing

STAGE_FIELDS = (
    "x4u_days_purchasing",
    "x4u_days_approval",
    "x4u_days_supplier",
    "x4u_days_warehouse",
    "x4u_days_assembly",
    "x4u_days_dispatch",
    "x4u_days_total",
    "x4u_delay_stage",
    "x4u_delay_days",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    set_costing(env)
    trigger = env.ref("quality_control_mrp_oca.qc_trigger_mrp", raise_if_not_found=False)
    if trigger:
        env["qc.trigger.product_category_line"].search(
            [("trigger", "=", trigger.id), ("product_category", "=", env.ref("x4u_setup_base.categ_generators").id)]
        ).unlink()
    params = env["ir.config_parameter"].sudo()
    for key in ("x4u_job_order.qc_user_id", "x4u_job_order.target_qc_days"):
        params.set_param(key, False)
    jobs = env["mrp.production"].search([("x4u_is_job_order", "=", True)])
    for name in STAGE_FIELDS:
        env.add_to_compute(jobs._fields[name], jobs)
    jobs.flush_recordset(list(STAGE_FIELDS))
