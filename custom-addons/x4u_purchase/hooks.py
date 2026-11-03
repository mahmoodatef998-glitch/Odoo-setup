def post_init_hook(env):
    """The POs from before this module get the payment schedule of their terms (spec P4)."""
    env["purchase.order"].search([("x4u_schedule_ids", "=", False), ("state", "!=", "cancel")])._x4u_fill_schedule()
