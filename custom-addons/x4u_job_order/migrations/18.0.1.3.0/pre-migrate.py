"""Spec v0.4 (2026-10-27): no inspection step. "Finished" now means the generator is in
stock (was "Assembled & Tested"), and "Delivered" means it is at the customer (was "Finished")."""


def migrate(cr, version):
    cr.execute("UPDATE mrp_production SET x4u_job_state = 'delivered' WHERE x4u_job_state = 'finished'")
    cr.execute("UPDATE mrp_production SET x4u_job_state = 'finished' WHERE x4u_job_state = 'assembled'")
    cr.execute("UPDATE x4u_job_order_event SET event_type = 'finished' WHERE event_type = 'assembled'")
    cr.execute("UPDATE mrp_production SET x4u_delay_stage = NULL WHERE x4u_delay_stage = 'qc'")
