from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import X4uGeneratorCommon


@tagged("post_install", "-at_install")
class TestGeneratorSecurity(X4uGeneratorCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_b = cls.env["res.company"].create({"name": "X4U Test Company B"})
        cls.stock_user_b = new_test_user(
            cls.env,
            login="x4u_stock_user_b",
            groups="base.group_user,stock.group_stock_user",
            company_id=cls.company_b.id,
            company_ids=[Command.set(cls.company_b.ids)],
        )
        cls.salesman = new_test_user(
            cls.env,
            login="x4u_salesman",
            groups="base.group_user,sales_team.group_sale_salesman",
        )
        cls.card = cls._create_lot("X4U-T9-0001").x4u_generator_id

    # T9 - multi-company record rules
    def test_other_company_cannot_see_card(self):
        self.assertEqual(self.card.company_id, self.company)
        Generator = self.env["x4u.generator"].with_user(self.stock_user_b)
        self.assertFalse(Generator.search([("id", "=", self.card.id)]))
        with self.assertRaises(AccessError):
            self.card.with_user(self.stock_user_b).read(["name"])
        reading = self._create_reading(self.card, 5.0)
        with self.assertRaises(AccessError):
            reading.with_user(self.stock_user_b).read(["hours"])

    def test_salesman_has_read_only_access(self):
        card = self.card.with_user(self.salesman)
        card.read(["name", "kva_prime", "state", "warranty_state", "qc_state"])
        # The form shows the serial and delivery names without stock rights.
        card.web_read(
            {
                "lot_id": {"fields": {"display_name": {}}},
                "delivery_picking_id": {"fields": {"display_name": {}}},
            }
        )
        with self.assertRaises(AccessError):
            card.write({"engine_serial": "X"})
        with self.assertRaises(AccessError):
            self.env["x4u.generator.hour.reading"].with_user(self.salesman).create(
                {
                    "generator_id": self.card.id,
                    "hours": 1.0,
                    "date": fields.Datetime.now(),
                }
            )

    def test_only_inventory_admin_can_delete(self):
        with self.assertRaises(AccessError):
            self.card.with_user(self.stock_user).unlink()
        self.card.with_user(self.stock_manager).unlink()
        self.assertFalse(self.card.exists())
