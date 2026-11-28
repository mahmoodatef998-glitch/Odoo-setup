import io
import zipfile
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestX4uStockValue(TransactionCase):
    """Spec §23: Stock Value on a date - by category and product, each serial at its own cost, the
    same total as the stock accounts in the books."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.vendor = cls.env["res.partner"].create({"name": "X4U Test Stock Value Vendor"})
        engines = cls.env.ref("x4u_setup_base.categ_engines")
        alternators = cls.env.ref("x4u_setup_base.categ_alternators")
        cls.engine = cls.env["product.product"].create(
            {"name": "X4U Test SV Engine", "is_storable": True, "categ_id": engines.id, "tracking": "serial"}
        )
        cls.alternator = cls.env["product.product"].create(
            {"name": "X4U Test SV Alternator", "is_storable": True, "categ_id": alternators.id}
        )

    def _receive(self, product, qty, price):
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        suppliers = self.env.ref("stock.stock_location_suppliers")
        receipt = self.env["stock.picking"].create(
            {
                "partner_id": self.vendor.id,
                "picking_type_id": warehouse.in_type_id.id,
                "location_id": suppliers.id,
                "location_dest_id": warehouse.lot_stock_id.id,
                "move_ids": [
                    Command.create(
                        {
                            "name": product.name,
                            "product_id": product.id,
                            "product_uom_qty": qty,
                            "product_uom": product.uom_id.id,
                            "price_unit": price,
                            "location_id": suppliers.id,
                            "location_dest_id": warehouse.lot_stock_id.id,
                        }
                    )
                ],
            }
        )
        receipt.action_confirm()
        receipt.move_ids.quantity = qty
        for number, line in enumerate(receipt.move_line_ids, 1):
            if line.product_id.tracking == "serial":
                line.lot_name = "X4U-SV-%s-%s" % (receipt.id, number)
        for move in receipt.move_ids:
            if "x4u_alternator_serials" in move._fields and move.x4u_role == "alternator":
                move.x4u_alternator_serials = ", ".join("X4U-SVA-%s-%s" % (move.id, n) for n in range(1, int(qty) + 1))
        receipt.move_ids.picked = True
        receipt.button_validate()
        return receipt

    def _report(self, date=None, user=None):
        Wizard = self.env["x4u.stock.value"].with_user(user) if user else self.env["x4u.stock.value"]
        wizard = Wizard.create({"date": date or fields.Date.today()})
        wizard.action_view()
        return wizard

    def test_value_by_product_and_serial(self):
        self._receive(self.engine, 1, 9000.0)
        self._receive(self.engine, 1, 10000.0)
        self._receive(self.alternator, 2, 1500.0)
        wizard = self._report()
        engine = wizard.line_ids.filtered(lambda line: line.product_id == self.engine)
        self.assertEqual((engine.quantity, engine.value, engine.unit_cost, engine.serial_count), (2.0, 19000.0, 9500.0, 2))
        self.assertEqual(sorted(engine.lot_ids.mapped("value")), [9000.0, 10000.0], "each serial at its own cost")
        self.assertEqual(engine.categ_id, self.env.ref("x4u_setup_base.categ_engines"))
        alternator = wizard.line_ids.filtered(lambda line: line.product_id == self.alternator)
        self.assertEqual((alternator.quantity, alternator.value, alternator.unit_cost), (2.0, 3000.0, 1500.0))
        self.assertFalse(alternator.lot_ids, "valued at the average: no serial lines")
        # The total is the books': every stock entry was posted on the categories' stock accounts.
        self.assertAlmostEqual(wizard.total_value, sum(wizard.line_ids.mapped("value")))
        self.assertAlmostEqual(wizard.difference, 0.0)
        self.assertAlmostEqual(wizard.book_balance, wizard.total_value)
        self.assertTrue(wizard.account_ids, "the stock accounts, each against its stock value")

    def test_value_on_a_date(self):
        self._receive(self.engine, 1, 9000.0)
        yesterday = self._report(fields.Date.today() - timedelta(days=1))
        self.assertNotIn(self.engine, yesterday.line_ids.product_id, "not in stock yet yesterday")

    def test_delivered_serial_leaves_the_value(self):
        receipt = self._receive(self.engine, 2, 9000.0)
        lot = receipt.move_line_ids.lot_id[:1]
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        scrap = self.env["stock.scrap"].create(
            {"product_id": self.engine.id, "lot_id": lot.id, "scrap_qty": 1, "location_id": warehouse.lot_stock_id.id}
        )
        scrap.action_validate()
        engine = self._report().line_ids.filtered(lambda line: line.product_id == self.engine)
        self.assertEqual((engine.quantity, engine.value, engine.serial_count), (1.0, 9000.0, 1))

    def test_excel_and_who_sees_it(self):
        self._receive(self.engine, 1, 9000.0)
        wizard = self._report()
        content, kind = self.env["ir.actions.report"]._render_xlsx(
            "x4u_account.action_report_x4u_stock_value_xlsx", wizard.ids, {}
        )
        self.assertEqual(kind, "xlsx")
        with zipfile.ZipFile(io.BytesIO(content)) as book:
            xml = b"".join(book.read(name) for name in book.namelist() if name.endswith(".xml"))
        for text in (b"Stock Value", b"Serials", b"X4U Test SV Engine", b"Difference"):
            self.assertIn(text, xml)
        storekeeper = new_test_user(self.env, login="x4u_sv_store", groups="base.group_user,stock.group_stock_user")
        self.assertTrue(self._report(user=storekeeper).line_ids)
        menu = self.env.ref("x4u_account.menu_x4u_stock_value_inventory")
        salesperson = new_test_user(self.env, login="x4u_sv_sales", groups="base.group_user,sales_team.group_sale_salesman")
        self.assertNotIn(menu.id, self.env["ir.ui.menu"].with_user(salesperson)._visible_menu_ids(), "the costs are in it")
        self.assertIn(menu.id, self.env["ir.ui.menu"].with_user(storekeeper)._visible_menu_ids())
