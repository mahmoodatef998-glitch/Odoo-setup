from datetime import timedelta

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged
from odoo.tools import mute_logger

from .common import X4uGeneratorCommon


@tagged("post_install", "-at_install")
class TestGeneratorCard(X4uGeneratorCommon):
    # T1 - card created from the serial, specs copied from the product
    def test_card_created_for_generator_serial(self):
        lot = self._create_lot("X4U-T1-0001")
        card = lot.x4u_generator_id
        self.assertTrue(card)
        self.assertEqual(card.name, "X4U-T1-0001")
        self.assertEqual(card.product_id, self.generator_product)
        # Shared product: the lot has no company, the card takes the current one.
        self.assertFalse(lot.company_id)
        self.assertEqual(card.company_id, self.env.company)
        self.assertEqual(card.kva_prime, 100.0)
        self.assertEqual(card.kva_standby, 110.0)
        self.assertEqual(card.engine_brand_id, self.engine_brand)
        self.assertEqual(card.engine_model, "E-100")
        self.assertEqual(card.alternator_brand_id, self.alternator_brand)
        self.assertEqual(card.alternator_model, "A-100")
        self.assertEqual(card.warranty_months, 12)
        self.assertEqual(card.warranty_hours, 1000.0)
        self.assertEqual(card.state, "in_stock")
        self.assertEqual(card.warranty_state, "not_started")
        self.assertEqual(card.qc_state, "none")

    def test_no_card_for_regular_product(self):
        lot = self._create_lot("X4U-T1-PART", self.part_product)
        self.assertFalse(lot.x4u_generator_ids)

    def test_card_specs_editable_per_unit(self):
        card = self._create_lot("X4U-T1-0002").x4u_generator_id
        card.alternator_model = "A-100-SPECIAL"
        self.assertEqual(card.alternator_model, "A-100-SPECIAL")
        self.assertEqual(self.generator_product.x4u_alternator_model, "A-100")

    def test_create_card_button_for_existing_lot(self):
        lot = self._create_lot("X4U-T1-OLD", self.part_product)
        self.part_product.write({"x4u_is_generator": True, "x4u_kva_prime": 20.0})
        self.assertFalse(lot.x4u_generator_ids)
        action = lot.action_x4u_create_generator_card()
        card = lot.x4u_generator_id
        self.assertEqual(action["res_id"], card.id)
        self.assertEqual(card.kva_prime, 20.0)
        lot.action_x4u_create_generator_card()
        self.assertEqual(len(lot.x4u_generator_ids), 1)

    def test_card_form_fills_specs_from_lot(self):
        lot = self._create_lot("X4U-T1-FORM")
        lot.x4u_generator_id.unlink()
        with Form(self.env["x4u.generator"]) as form:
            form.lot_id = lot
            self.assertEqual(form.kva_prime, 100.0)
            self.assertEqual(form.engine_brand_id, self.engine_brand)
        self.assertEqual(lot.x4u_generator_id.alternator_model, "A-100")

    # T2 - generator products must be serial-tracked with a kVA rating
    def test_generator_product_rules(self):
        Product = self.env["product.product"]
        with self.assertRaises(ValidationError):
            Product.create(
                {
                    "name": "Lot-tracked Genset",
                    "type": "consu",
                    "is_storable": True,
                    "tracking": "lot",
                    "x4u_is_generator": True,
                    "x4u_kva_prime": 50.0,
                }
            )
        with self.assertRaises(ValidationError):
            Product.create(
                {
                    "name": "Genset Without Rating",
                    "type": "consu",
                    "is_storable": True,
                    "tracking": "serial",
                    "x4u_is_generator": True,
                }
            )

    def test_product_form_onchange_sets_serial_tracking(self):
        with Form(self.env["product.template"]) as form:
            form.name = "X4U Form Genset"
            form.x4u_is_generator = True
            self.assertTrue(form.is_storable)
            self.assertEqual(form.tracking, "serial")
            form.x4u_kva_prime = 200.0
        self.assertTrue(form.record.x4u_is_generator)

    # T3 - one card per serial
    def test_one_card_per_lot(self):
        lot = self._create_lot("X4U-T3-0001")
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self.env["x4u.generator"].create({"lot_id": lot.id})
            self.env.flush_all()

    # T4 - running hours
    def test_running_hours_follow_latest_reading(self):
        card = self._create_lot("X4U-T4-0001").x4u_generator_id
        now = fields.Datetime.now()
        self._create_reading(card, 2.0, now - timedelta(days=10), "factory_test")
        self._create_reading(card, 150.0, now - timedelta(days=5))
        self.assertEqual(card.running_hours, 150.0)
        self.assertEqual(card.last_reading_date, now - timedelta(days=5))

    def test_running_hours_cannot_go_backwards(self):
        card = self._create_lot("X4U-T4-0002").x4u_generator_id
        now = fields.Datetime.now()
        self._create_reading(card, 2.0, now - timedelta(days=10))
        self._create_reading(card, 150.0, now - timedelta(days=5))
        with self.assertRaises(ValidationError):
            self._create_reading(card, 100.0, now)
        with self.assertRaises(ValidationError):
            self._create_reading(card, 10.0, now - timedelta(days=20))
        with self.assertRaises(ValidationError):
            self._create_reading(card, -1.0, now - timedelta(days=30))
        card.invalidate_recordset()
        self.assertEqual(card.running_hours, 150.0)

    # T5 - warranty
    def test_warranty_dates_follow_delivery_then_commissioning(self):
        card = self._create_lot("X4U-T5-0001").x4u_generator_id
        today = fields.Date.context_today(card)
        delivery = today - relativedelta(months=2)
        card.delivery_date = delivery
        self.assertEqual(card.state, "delivered")
        self.assertEqual(card.warranty_start_date, delivery)
        self.assertEqual(card.warranty_end_date, delivery + relativedelta(months=12))
        self.assertEqual(card.warranty_state, "active")
        commissioning = today - relativedelta(months=1)
        card.commissioning_date = commissioning
        self.assertEqual(card.state, "commissioned")
        self.assertEqual(card.warranty_start_date, commissioning)
        self.assertEqual(
            card.warranty_end_date, commissioning + relativedelta(months=12)
        )

    def test_warranty_capped_from_delivery(self):
        card = self._create_lot("X4U-T5-0002").x4u_generator_id
        delivery = fields.Date.context_today(card) - relativedelta(months=11)
        card.write(
            {
                "delivery_date": delivery,
                "commissioning_date": delivery + relativedelta(months=10),
                "warranty_max_delivery_months": 18,
            }
        )
        # 10 + 12 months from commissioning would be 22 months; the cap wins.
        self.assertEqual(card.warranty_end_date, delivery + relativedelta(months=18))

    def test_warranty_expired_by_time(self):
        card = self._create_lot("X4U-T5-0003").x4u_generator_id
        card.delivery_date = fields.Date.context_today(card) - relativedelta(months=13)
        self.assertEqual(card.warranty_state, "expired")

    def test_warranty_expired_by_hours_first(self):
        card = self._create_lot("X4U-T5-0004").x4u_generator_id
        card.delivery_date = fields.Date.context_today(card) - relativedelta(months=1)
        self._create_reading(card, 999.0)
        self.assertEqual(card.warranty_state, "active")
        self._create_reading(card, 1000.0, fields.Datetime.now() + timedelta(minutes=1))
        self.assertEqual(card.warranty_state, "expired")

    def test_warranty_without_hours_limit(self):
        card = self._create_lot("X4U-T5-0005").x4u_generator_id
        card.write(
            {
                "warranty_hours": 0.0,
                "delivery_date": fields.Date.context_today(card)
                - relativedelta(months=1),
            }
        )
        self._create_reading(card, 5000.0)
        self.assertEqual(card.warranty_state, "active")

    def test_cron_expires_warranty_when_time_passes(self):
        card = self._create_lot("X4U-T5-CRON").x4u_generator_id
        past = fields.Date.today() - relativedelta(months=13)
        with freeze_time(past):
            card.delivery_date = past
            card.flush_recordset()
            self.assertEqual(card.warranty_state, "active")
        # The stored state is stale until the daily cron runs.
        self.assertEqual(card.warranty_state, "active")
        self.env["x4u.generator"]._cron_update_warranty_state()
        self.assertEqual(card.warranty_state, "expired")

    def test_commissioning_needs_delivery(self):
        card = self._create_lot("X4U-T5-0006").x4u_generator_id
        today = fields.Date.context_today(card)
        with self.assertRaises(ValidationError):
            card.commissioning_date = today
        card.delivery_date = today
        with self.assertRaises(ValidationError):
            card.commissioning_date = today - timedelta(days=1)

    # T8 - quality status follows the latest inspection of the serial
    def test_qc_state_follows_inspections(self):
        lot = self._create_lot("X4U-T8-0001")
        card = lot.x4u_generator_id
        self.assertEqual(card.qc_state, "none")
        inspection = self._create_inspection(lot, "draft")
        self.assertEqual(card.qc_state, "pending")
        self.assertEqual(card.qc_inspection_count, 1)
        inspection.state = "failed"
        self.assertEqual(card.qc_state, "failed")
        inspection.state = "success"
        self.assertEqual(card.qc_state, "passed")
        inspection.state = "canceled"
        self.assertEqual(card.qc_state, "none")
