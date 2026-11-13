from collections import defaultdict

from odoo import Command
from odoo.tests import Form, TransactionCase, new_test_user


class X4uJobOrderCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.env.company.id)], limit=1)
        buy = ref("purchase_stock.route_warehouse0_buy")
        mto = ref("stock.route_warehouse0_mto")
        manufacture = ref("mrp.route_warehouse0_manufacture")
        Partner = cls.env["res.partner"]
        cls.customer = Partner.create({"name": "X4U Test Customer"})
        cls.vendor_engine = Partner.create({"name": "X4U Test Engine Supplier"})
        cls.vendor_aqt = Partner.create({"name": "X4U Test AQT"})

        def component(name, categ):
            return cls.env["product.product"].create(
                {
                    "name": name,
                    "is_storable": True,
                    "categ_id": ref("x4u_setup_base." + categ).id,
                    "purchase_request": True,
                    "route_ids": [Command.set([buy.id, mto.id])],
                }
            )

        cls.engine = component("X4U Test Engine E-500", "categ_engines")
        cls.alt_aqt = component("X4U Test Alternator AQT", "categ_alternators")
        cls.alt_leroy = component("X4U Test Alternator TAL-A47-B", "categ_alternators")
        cls.alt_stamford = component("X4U Test Alternator HCI544D", "categ_alternators")
        cls.body_open = component("X4U Test Body Open", "categ_bodies")
        cls.body_canopy = component("X4U Test Body Canopy", "categ_bodies")

        enclosure = ref("x4u_setup_base.attr_enclosure")
        alternator = ref("x4u_setup_base.attr_alternator")
        cls.template = cls.env["product.template"].create(
            {
                "name": "X4U Test AQT-500",
                "is_storable": True,
                "tracking": "serial",
                "x4u_is_generator": True,
                "x4u_kva_prime": 455.0,
                "x4u_kva_standby": 500.0,
                "route_ids": [Command.set([manufacture.id, mto.id])],
                "attribute_line_ids": [
                    Command.create({"attribute_id": enclosure.id, "value_ids": [Command.set(enclosure.value_ids.ids)]}),
                    Command.create({"attribute_id": alternator.id, "value_ids": [Command.set(alternator.value_ids.ids)]}),
                ],
            }
        )
        ptavs = cls.template.attribute_line_ids.product_template_value_ids

        def ptav(xmlid):
            return ptavs.filtered(lambda v: v.product_attribute_value_id == ref("x4u_setup_base." + xmlid))

        def line(product, value=None):
            vals = {"product_id": product.id, "product_qty": 1}
            if value:
                vals["bom_product_template_attribute_value_ids"] = [Command.set(ptav(value).ids)]
            return Command.create(vals)

        cls.env["mrp.bom"].create(
            {
                "product_tmpl_id": cls.template.id,
                "bom_line_ids": [
                    line(cls.engine),
                    line(cls.alt_aqt, "attr_alternator_aqt"),
                    line(cls.alt_leroy, "attr_alternator_leroy"),
                    line(cls.alt_stamford, "attr_alternator_stamford"),
                    line(cls.body_open, "attr_enclosure_open"),
                    line(cls.body_canopy, "attr_enclosure_canopy"),
                ],
            }
        )
        cls.variant = cls.template._create_product_variant(
            ptav("attr_enclosure_canopy") + ptav("attr_alternator_stamford")
        )
        Brand = cls.env["x4u.generator.brand"]
        if not Brand.search([("name", "=ilike", "Stamford")]):
            Brand.create({"name": "Stamford", "brand_type": "alternator"})
        cls.manager = new_test_user(
            cls.env,
            login="x4u_jo_manager",
            groups="base.group_user,stock.group_stock_manager,purchase.group_purchase_manager,"
            "mrp.group_mrp_manager,sales_team.group_sale_manager",
        )
        cls.buyer = new_test_user(
            cls.env,
            login="x4u_jo_buyer",
            groups="base.group_user,purchase.group_purchase_user,purchase_request.group_purchase_request_user",
        )
        cls.salesman = new_test_user(
            cls.env, login="x4u_jo_salesman", groups="base.group_user,sales_team.group_sale_salesman"
        )
        cls.storekeeper = new_test_user(
            cls.env,
            login="x4u_jo_storekeeper",
            groups="base.group_user,stock.group_stock_user,x4u_job_order.group_x4u_job_order_viewer",
        )
        cls.operation = new_test_user(cls.env, login="x4u_jo_operation", groups="base.group_user,mrp.group_mrp_user")

    def _sell(self, **values):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "warehouse_id": self.warehouse.id,
                "order_line": [Command.create({"product_id": self.variant.id, "product_uom_qty": 1})],
                **values,
            }
        )
        order.action_confirm()
        return order, order.mrp_production_ids

    def _order_parts(self, production):
        """Purchasing picks the vendor per line: engine + alternator from one, body from AQT."""
        lines = production._x4u_purchase_requests().line_ids
        Wizard = self.env["purchase.request.line.make.purchase.order"]
        for vendor, products in (
            (self.vendor_engine, self.engine | self.alt_stamford),
            (self.vendor_aqt, self.body_canopy),
        ):
            selected = lines.filtered(lambda line, p=products: line.product_id in p)
            wizard = Wizard.with_context(active_model="purchase.request.line", active_ids=selected.ids).create(
                {"supplier_id": vendor.id}
            )
            wizard.make_purchase_order()
        return self.env["purchase.order"].search(
            [("order_line.move_dest_ids", "in", production._x4u_component_moves().ids)]
        )

    def _validate(self, picking):
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            if move.picking_code == "incoming" and move.has_tracking == "serial" and not move.product_id.x4u_is_generator:
                # Every engine comes in with its serial (spec v0.8 N1-N2).
                for number, line in enumerate(move.move_line_ids.filtered(lambda ml: not ml.lot_id and not ml.lot_name), 1):
                    line.lot_name = "X4U-SN-%s-%s" % (move.id, number)
        picking.move_ids.picked = True
        res = picking.button_validate()
        if isinstance(res, dict) and res.get("res_model") == "x4u.ready.receipt":
            # A ready generator comes in with the serial of its engine (spec v0.8 N7).
            wizard = self.env[res["res_model"]].browse(res["res_id"])
            for line in wizard.line_ids:
                line.engine_serial = "X4U-E-%s" % line.ready_order_id.name
            wizard.action_confirm()
        self.assertEqual(picking.state, "done")

    def _receipt(self, product, quantity, price=0.0):
        """A receipt of a part from the supplier into WH/Stock, confirmed, not validated."""
        suppliers = self.env.ref("stock.stock_location_suppliers")
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.warehouse.in_type_id.id,
                "location_id": suppliers.id,
                "location_dest_id": self.warehouse.lot_stock_id.id,
                "move_ids": [
                    Command.create(
                        {
                            "name": product.name,
                            "product_id": product.id,
                            "product_uom_qty": quantity,
                            "product_uom": product.uom_id.id,
                            "price_unit": price,
                            "location_id": suppliers.id,
                            "location_dest_id": self.warehouse.lot_stock_id.id,
                        }
                    )
                ],
            }
        )
        picking.action_confirm()
        return picking

    def _stock(self, product, quantity, price=None):
        """Parts come into WH/Stock by a receipt, engines with their serials."""
        self._validate(self._receipt(product, quantity, price if price is not None else product.standard_price or 100.0))

    def _lots(self, product):
        """Serials of the product in WH/Stock."""
        return self.env["stock.quant"].search(
            [("product_id", "=", product.id), ("location_id", "child_of", self.warehouse.lot_stock_id.id), ("quantity", ">", 0)]
        ).lot_id

    def _deliver_material(self, production):
        self._validate(production.picking_ids.filtered(lambda p: p.picking_type_id == self.warehouse.pbm_type_id))

    def _deliver_materials(self, production, quantities=None, lots=None):
        """Deliver Materials as the Storekeeper: by product, or what the screen proposes; an engine
        with the serials given, or the first ones in stock (spec v0.8 N3)."""
        action = production.with_user(self.storekeeper).action_x4u_deliver_materials()
        wizard = self.env[action["res_model"]].with_user(self.storekeeper).browse(action["res_id"])
        used = defaultdict(float)
        taken = self.env["stock.lot"]
        for line in wizard.line_ids:
            product = line.product_id
            # Engines and alternators have one line per unit (spec v0.8.1).
            per_unit = line.tracking == "serial" or line.x4u_role == "alternator"
            if quantities is not None:
                want = quantities.get(product, 0.0)
                line.quantity = (1.0 if want - used[product] >= 1 else 0.0) if per_unit else want
                used[product] += line.quantity
            if line.tracking == "serial":
                if quantities is None or line.quantity:
                    pool = ((lots or {}).get(product) or line.available_lot_ids) - taken
                    line.lot_id = pool.sorted("name")[:1]
                    taken |= line.lot_id
                else:
                    line.lot_id = False
        wizard.action_confirm()

    def _produce(self, production):
        with Form(production) as form:
            form.qty_producing = 1
        production.move_raw_ids.picked = True
        production.button_mark_done()

    def _deliver(self, order):
        self._validate(order.picking_ids.filtered(lambda p: p.picking_type_code == "outgoing"))
