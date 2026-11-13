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


def setup_job_analytic(env):
    """Spec v0.5 A1-A2: analytic accounting on (the Analytic column on invoice and bill lines),
    and an analytic account for every Job Order that has none yet, carried to its sales line,
    its invoice lines and their cost of sales."""
    env["res.config.settings"].create({"group_analytic_accounting": True}).execute()
    jobs = env["mrp.production"].search(
        [("x4u_is_job_order", "=", True), ("state", "!=", "cancel")], order="id"
    )
    jobs._x4u_job_analytic(backfill=True)


def setup_engine_serials(env):
    """Spec v0.8 N1: every engine is tracked and valued by its serial. Engines already in stock
    without one get a serial first (<code>-001, -002...) by a stock count, then Odoo re-values
    them per serial."""
    engines = env.ref("x4u_setup_base.categ_engines", raise_if_not_found=False)
    if not engines:
        return
    templates = env["product.template"].with_context(active_test=False).search(
        [("categ_id", "child_of", engines.id), ("is_storable", "=", True), ("tracking", "!=", "serial")]
    )
    Quant = env["stock.quant"]
    Lot = env["stock.lot"]
    for template in templates:
        template.write({"tracking": "serial", "lot_valuated": False})
        for product in template.product_variant_ids:
            loose = Quant.search(
                [("product_id", "=", product.id), ("location_id.usage", "=", "internal"), ("lot_id", "=", False), ("quantity", ">", 0)]
            )
            if not loose:
                continue
            code = product.default_code or "ENG%s" % product.id
            counted = Quant
            number = 0
            for quant in loose:
                units = int(quant.quantity)
                quant.with_context(inventory_mode=True).write({"inventory_quantity": quant.quantity - units})
                counted |= quant
                for _unit in range(units):
                    number += 1
                    lot = Lot.create({"name": "%s-%03d" % (code, number), "product_id": product.id, "company_id": quant.company_id.id})
                    counted |= Quant.with_context(inventory_mode=True).create(
                        {"product_id": product.id, "location_id": quant.location_id.id, "lot_id": lot.id, "inventory_quantity": 1}
                    )
            counted._apply_inventory()
    templates.write({"lot_valuated": True})


def post_init_hook(env):
    set_costing(env)
    setup_job_analytic(env)
    setup_engine_serials(env)
