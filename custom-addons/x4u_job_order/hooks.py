COSTED_CATEGORIES = ("categ_generators", "categ_components", "categ_engines", "categ_alternators", "categ_bodies")


def set_costing(env):
    """Parts at what was paid for them (FIFO), so a generator's value is its parts plus
    the overhead (spec v0.4 V5 / V6). Each generator keeps its own value (per serial)."""
    for xmlid in COSTED_CATEGORIES:
        category = env.ref("x4u_setup_base." + xmlid, raise_if_not_found=False)
        if category and category.property_cost_method != "fifo":
            category.property_cost_method = "fifo"
    env["product.template"].with_context(active_test=False).search(
        [("x4u_is_generator", "=", True), ("tracking", "=", "serial"), ("lot_valuated", "=", False)]
    ).lot_valuated = True


def post_init_hook(env):
    set_costing(env)
