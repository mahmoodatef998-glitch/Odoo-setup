from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user


class X4uGeneratorCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        Brand = cls.env["x4u.generator.brand"]
        cls.engine_brand = Brand.create(
            {"name": "X4U Test Engine", "brand_type": "engine"}
        )
        cls.alternator_brand = Brand.create(
            {"name": "X4U Test Alternator", "brand_type": "alternator"}
        )
        cls.generator_product = cls.env["product.product"].create(
            {
                "name": "X4U Test Genset 100 kVA",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "x4u_is_generator": True,
                "x4u_kva_prime": 100.0,
                "x4u_kva_standby": 110.0,
                "x4u_engine_brand_id": cls.engine_brand.id,
                "x4u_engine_model": "E-100",
                "x4u_alternator_brand_id": cls.alternator_brand.id,
                "x4u_alternator_model": "A-100",
                "x4u_warranty_months": 12,
                "x4u_warranty_hours": 1000.0,
            }
        )
        cls.part_product = cls.env["product.product"].create(
            {
                "name": "X4U Test Spare Part",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
            }
        )
        cls.customer = cls.env["res.partner"].create({"name": "X4U Test Customer"})
        cls.stock_user = new_test_user(
            cls.env,
            login="x4u_stock_user",
            groups="base.group_user,stock.group_stock_user",
        )
        cls.stock_manager = new_test_user(
            cls.env,
            login="x4u_stock_manager",
            groups="base.group_user,stock.group_stock_manager",
        )

    @classmethod
    def _create_lot(cls, name, product=None):
        return cls.env["stock.lot"].create(
            {"name": name, "product_id": (product or cls.generator_product).id}
        )

    def _create_inspection(self, lot, state):
        return self.env["qc.inspection"].create(
            {"object_id": f"stock.lot,{lot.id}", "state": state}
        )

    def _create_reading(self, card, hours, date=None, source="service"):
        return self.env["x4u.generator.hour.reading"].create(
            {
                "generator_id": card.id,
                "hours": hours,
                "date": date or fields.Datetime.now(),
                "source": source,
            }
        )

    def _sell(self, lot):
        """Put the serial in stock and confirm a sales order for it."""
        self.env["stock.quant"]._update_available_quantity(
            lot.product_id, self.warehouse.lot_stock_id, 1.0, lot_id=lot
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "warehouse_id": self.warehouse.id,
                "order_line": [
                    Command.create(
                        {"product_id": lot.product_id.id, "product_uom_qty": 1.0}
                    )
                ],
            }
        )
        order.action_confirm()
        picking = order.picking_ids
        self.assertEqual(picking.move_line_ids.lot_id, lot)
        return order, picking

    def _validate(self, picking, user):
        picking.move_ids.picked = True
        picking.with_user(user).button_validate()
        self.assertEqual(picking.state, "done")

    def _return(self, picking, user):
        """Return a delivered serial to stock."""
        lot = picking.move_line_ids.lot_id
        wizard = (
            self.env["stock.return.picking"]
            .with_context(active_id=picking.id, active_model="stock.picking")
            .create({})
        )
        return_picking = self.env["stock.picking"].browse(
            wizard.action_create_returns_all()["res_id"]
        )
        return_picking.action_assign()
        move = return_picking.move_ids
        if not move.move_line_ids:
            move.quantity = 1.0
        move.move_line_ids.write({"lot_id": lot.id, "quantity": 1.0})
        self._validate(return_picking, user)
        return return_picking
