COSTED_CATEGORIES = (
    "categ_generators", "categ_components", "categ_engines", "categ_alternators", "categ_bodies", "categ_ckd",
)


def set_costing(env):
    """Parts at what was paid for them, so a generator's value is its parts plus the overhead
    (spec v0.4 V5 / V6). Each engine, CKD, body and generator keeps its own value (per serial); the
    others at the average of what was paid (x4u_account spec §20 P1, which also moves FIFO to average
    on a database with stock)."""
    for xmlid in COSTED_CATEGORIES:
        category = env.ref("x4u_setup_base." + xmlid, raise_if_not_found=False)
        if category and category.property_cost_method not in ("fifo", "average"):
            category.property_cost_method = "average"
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


# Spec v0.8 N1 / v0.9 C1 / v0.10 B1: the parts tracked and valued by their serial; prefix of the
# serials given to the ones already in stock when the product has no internal reference.
SERIAL_PARTS = (("categ_engines", "ENG"), ("categ_ckd", "CKD"), ("categ_bodies", "BODY"))


def setup_engine_serials(env):
    """Spec v0.8 N1 / v0.10 B4: every engine, CKD and genset body is tracked and valued by its
    serial. Those already in stock without one (in WH/Stock or delivered to the factory) get a serial
    first (<code>-001, -002...) by a stock count, then Odoo re-values them per serial."""
    Quant = env["stock.quant"]
    Lot = env["stock.lot"]
    for xmlid, prefix in SERIAL_PARTS:
        category = env.ref("x4u_setup_base." + xmlid, raise_if_not_found=False)
        if not category:
            continue
        templates = env["product.template"].with_context(active_test=False).search(
            [("categ_id", "child_of", category.id), ("is_storable", "=", True), ("tracking", "!=", "serial")]
        )
        for template in templates:
            template.write({"tracking": "serial", "lot_valuated": False})
            for product in template.product_variant_ids:
                loose = Quant.search(
                    [("product_id", "=", product.id), ("location_id.usage", "=", "internal"), ("lot_id", "=", False), ("quantity", ">", 0)]
                )
                if not loose:
                    continue
                code = product.default_code or "%s%s" % (prefix, product.id)
                counted = Quant
                number = 0
                for quant in loose:
                    units = int(quant.quantity)
                    quant.with_context(inventory_mode=True).write({"inventory_quantity": quant.quantity - units})
                    counted |= quant
                    for _unit in range(units):
                        number += 1
                        while Lot.search_count([("product_id", "=", product.id), ("name", "=", "%s-%03d" % (code, number))]):
                            number += 1
                        lot = Lot.create({"name": "%s-%03d" % (code, number), "product_id": product.id, "company_id": quant.company_id.id})
                        counted |= Quant.with_context(inventory_mode=True).create(
                            {"product_id": product.id, "location_id": quant.location_id.id, "lot_id": lot.id, "inventory_quantity": 1}
                        )
                counted._apply_inventory()
        templates.write({"lot_valuated": True})


def use_4u_quotation_report(env):
    """x4u_generator_datasheet §9: the quotation sent by email is the 4U one (QT 1112 layout)."""
    template = env.ref("sale.email_template_edi_sale", raise_if_not_found=False)
    report = env.ref("x4u_job_order.action_report_x4u_quotation", raise_if_not_found=False)
    if template and report and template.report_template_ids != report:
        template.report_template_ids = [(6, 0, report.ids)]


def post_init_hook(env):
    use_4u_quotation_report(env)
    set_costing(env)
    setup_job_analytic(env)
    setup_engine_serials(env)
