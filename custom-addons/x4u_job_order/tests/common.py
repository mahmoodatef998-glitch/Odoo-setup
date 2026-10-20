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

    def _sell(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "warehouse_id": self.warehouse.id,
                "order_line": [Command.create({"product_id": self.variant.id, "product_uom_qty": 1})],
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
        picking.move_ids.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def _deliver_material(self, production):
        self._validate(production.picking_ids.filtered(lambda p: p.picking_type_id == self.warehouse.pbm_type_id))

    def _produce(self, production):
        with Form(production) as form:
            form.qty_producing = 1
        production.move_raw_ids.picked = True
        production.button_mark_done()

    def _inspect(self, production, state):
        inspection = self.env["qc.inspection"].create(
            {"object_id": "stock.lot,%s" % production.lot_producing_id.id, "state": "draft"}
        )
        inspection.state = state
        return inspection

    def _deliver(self, order):
        self._validate(order.picking_ids.filtered(lambda p: p.picking_type_code == "outgoing"))
