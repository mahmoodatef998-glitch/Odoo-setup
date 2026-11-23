"""Training database only: 4U-like sample data so the team can practise a whole cycle
(quotation -> PI and payment -> Job Order -> material requests and purchase -> Deliver
Materials -> Finish -> delivery -> tax invoice) before the pilot.

Runs inside "odoo shell" on a database whose name ends in _training (it refuses any other):
    docker compose run --rm -T web odoo shell -d odoo4u_training --no-http < scripts/training_data.py

Every record says (Training) or starts with TR-. Safe to run again: what exists is kept.
Also sets the "Training" label the navbar and the Home page show (x4u_theme).
"""

from odoo import Command

if not env.cr.dbname.endswith("_training"):
    raise SystemExit("training_data.py runs on a *_training database only, not on %r." % env.cr.dbname)

ref = env.ref
company = env.company
warehouse = env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
buy = ref("purchase_stock.route_warehouse0_buy")
mto = ref("stock.route_warehouse0_mto")
manufacture = ref("mrp.route_warehouse0_manufacture")
uae = ref("base.ae")

Partner = env["res.partner"]


def partner(name, city, customer=False):
    found = Partner.search([("name", "=", name)], limit=1)
    if found:
        return found
    return Partner.create(
        {
            "name": name,
            "is_company": True,
            "city": city,
            "country_id": uae.id,
            "customer_rank" if customer else "supplier_rank": 1,
        }
    )


vendor_engines = partner("Gulf Engines Trading (Training)", "Sharjah")
vendor_alternators = partner("Alternator Supplies FZE (Training)", "Ajman")
vendor_bodies = partner("Canopy Works LLC (Training)", "Sharjah")
for name, city in (
    ("Al Noor Contracting (Training)", "Dubai"),
    ("Emirates Facilities Management (Training)", "Abu Dhabi"),
    ("Sahara Projects LLC (Training)", "Al Ain"),
):
    partner(name, city, customer=True)

Product = env["product.product"]


def component(code, name, categ, vendor, cost):
    found = Product.search([("default_code", "=", code)], limit=1)
    if found:
        return found
    return Product.create(
        {
            "name": name,
            "default_code": code,
            "is_storable": True,
            "categ_id": ref("x4u_setup_base." + categ).id,
            "purchase_request": True,
            "route_ids": [Command.set([buy.id, mto.id])],
            "standard_price": cost,
            "seller_ids": [Command.create({"partner_id": vendor.id, "price": cost})],
        }
    )


enclosure = ref("x4u_setup_base.attr_enclosure")
alternator = ref("x4u_setup_base.attr_alternator")
open_ = ref("x4u_setup_base.attr_enclosure_open")
canopy = ref("x4u_setup_base.attr_enclosure_canopy")
aqt = ref("x4u_setup_base.attr_alternator_aqt")
leroy = ref("x4u_setup_base.attr_alternator_leroy")

# kVA standby, kVA prime, price (Open, AQT), extra for a canopy, extra for Leroy-Somer, part costs
MODELS = [
    (100, 90, 52000, 9000, 4000, {"engine": 21000, "aqt": 7000, "leroy": 10000, "open": 2500, "canopy": 8500}),
    (250, 225, 98000, 15000, 7000, {"engine": 42000, "aqt": 14000, "leroy": 19000, "open": 4000, "canopy": 14000}),
    (500, 455, 168000, 24000, 12000, {"engine": 78000, "aqt": 25000, "leroy": 34000, "open": 6500, "canopy": 22000}),
]

stock_plan = []  # (vendor, product, quantity)
for standby, prime, price, canopy_extra, leroy_extra, cost in MODELS:
    k = standby
    engine = component("TR-ENG%s" % k, "Diesel Engine for %s kVA (Training)" % k, "categ_engines", vendor_engines, cost["engine"])
    alt_aqt = component("TR-AQT%s" % k, "Alternator AQT %s kVA (Training)" % k, "categ_alternators", vendor_alternators, cost["aqt"])
    alt_leroy = component("TR-LS%s" % k, "Alternator Leroy-Somer %s kVA (Training)" % k, "categ_alternators", vendor_alternators, cost["leroy"])
    body_open = component("TR-OPEN%s" % k, "Open Skid Frame %s kVA (Training)" % k, "categ_bodies", vendor_bodies, cost["open"])
    body_canopy = component("TR-CAN%s" % k, "Soundproof Canopy %s kVA (Training)" % k, "categ_bodies", vendor_bodies, cost["canopy"])

    code = "TR-G%s" % k
    name = "Diesel Generator Set %s kVA (Training)" % k
    # Found by name: a template with variants keeps no code of its own.
    template = env["product.template"].search([("name", "=", name)], limit=1)
    if not template:
        template = env["product.template"].create(
            {
                "name": name,
                "categ_id": ref("x4u_setup_base.categ_generators").id,
                "is_storable": True,
                "tracking": "serial",
                "x4u_is_generator": True,
                "x4u_kva_prime": prime,
                "x4u_kva_standby": standby,
                "list_price": price,
                "route_ids": [Command.set([manufacture.id, mto.id])],
                "attribute_line_ids": [
                    Command.create({"attribute_id": enclosure.id, "value_ids": [Command.set((open_ | canopy).ids)]}),
                    Command.create({"attribute_id": alternator.id, "value_ids": [Command.set((aqt | leroy).ids)]}),
                ],
            }
        )
        ptavs = template.attribute_line_ids.product_template_value_ids

        def ptav(value):
            return ptavs.filtered(lambda v, value=value: v.product_attribute_value_id == value)

        ptav(canopy).price_extra = canopy_extra
        ptav(leroy).price_extra = leroy_extra

        def line(product, value=None):
            vals = {"product_id": product.id, "product_qty": 1}
            if value:
                vals["bom_product_template_attribute_value_ids"] = [Command.set(ptav(value).ids)]
            return Command.create(vals)

        env["mrp.bom"].create(
            {
                "product_tmpl_id": template.id,
                "bom_line_ids": [
                    line(engine),
                    line(alt_aqt, aqt),
                    line(alt_leroy, leroy),
                    line(body_open, open_),
                    line(body_canopy, canopy),
                ],
            }
        )
        for enc in (open_, canopy):
            for alt in (aqt, leroy):
                template._create_product_variant(ptav(enc) + ptav(alt))
    # Each variant its own code: TR-G100-OA = Open + AQT, TR-G100-CL = Canopy + Leroy-Somer.
    for variant in template.product_variant_ids:
        values = variant.product_template_attribute_value_ids.product_attribute_value_id
        suffix = ("C" if canopy in values else "O") + ("L" if leroy in values else "A")
        if variant.default_code != "%s-%s" % (code, suffix):
            variant.default_code = "%s-%s" % (code, suffix)
    stock_plan += [
        (vendor_engines, engine, 3),
        (vendor_alternators, alt_aqt, 2),
        (vendor_alternators, alt_leroy, 2),
        (vendor_bodies, body_open, 2),
        (vendor_bodies, body_canopy, 2),
    ]

# Starting stock: received from the vendors like the Storekeeper does, every engine and body
# with its serial, every alternator with its serial (x4u_job_order spec v0.8, v0.15).
Quant = env["stock.quant"]
suppliers = ref("stock.stock_location_suppliers")
received = 0
for vendor in (vendor_engines, vendor_alternators, vendor_bodies):
    lines = [
        (product, qty)
        for v, product, qty in stock_plan
        if v == vendor
        and not Quant.search_count([("product_id", "=", product.id), ("location_id", "child_of", warehouse.lot_stock_id.id), ("quantity", ">", 0)])
    ]
    if not lines:
        continue
    picking = env["stock.picking"].create(
        {
            "picking_type_id": warehouse.in_type_id.id,
            "partner_id": vendor.id,
            "origin": "Opening stock (Training)",
            "location_id": suppliers.id,
            "location_dest_id": warehouse.lot_stock_id.id,
            "move_ids": [
                Command.create(
                    {
                        "name": product.name,
                        "product_id": product.id,
                        "product_uom_qty": qty,
                        "product_uom": product.uom_id.id,
                        "price_unit": product.standard_price,
                        "location_id": suppliers.id,
                        "location_dest_id": warehouse.lot_stock_id.id,
                    }
                )
                for product, qty in lines
            ],
        }
    )
    picking.action_confirm()
    picking.action_assign()
    for move in picking.move_ids:
        move.quantity = move.product_uom_qty
        code = move.product_id.default_code.replace("TR-", "")
        if move.has_tracking == "serial":
            for number, ml in enumerate(move.move_line_ids, 1):
                ml.lot_name = "TR-%s-%02d" % (code, number)
        if move.x4u_role == "alternator" and not move.x4u_alternator_serials:
            move.x4u_alternator_serials = ", ".join("TR-%s-%02d" % (code, n) for n in range(1, int(move.quantity) + 1))
    picking.move_ids.picked = True
    picking.button_validate()
    received += len(picking.move_ids)

env["ir.config_parameter"].sudo().set_param("x4u_theme.environment_label", "Training")
env.cr.commit()

generators = env["product.product"].search([("default_code", "=like", "TR-G%")])
print("training: generators", len(generators.product_tmpl_id), "variants", len(generators))
print("training: parts in stock", sum(Quant.search([("product_id.default_code", "=like", "TR-%"), ("location_id", "child_of", warehouse.lot_stock_id.id)]).mapped("quantity")))
print("training: serials", env["stock.lot"].search_count([("name", "=like", "TR-%")]), "alternator serials", env["x4u.alternator.serial"].search_count([]))
print("training: moves received now", received, "| label", env["ir.config_parameter"].sudo().get_param("x4u_theme.environment_label"))
