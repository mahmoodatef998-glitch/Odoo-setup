from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, new_test_user, tagged

from .common import X4uJobOrderCommon


@tagged("post_install", "-at_install")
class TestJobOrder(X4uJobOrderCommon):
    # T1 + T6: the sale opens the Job Order with the parts of the variant sold
    def test_sale_opens_job_order(self):
        order, production = self._sell()
        self.assertEqual(len(production), 1)
        self.assertRegex(production.name, r"^4U-PO-\d{3,}$")
        self.assertEqual(production.x4u_sale_order_id, order)
        self.assertEqual(production.x4u_job_state, "waiting_parts")
        self.assertEqual(
            set(production.move_raw_ids.product_id.ids),
            {self.engine.id, self.alt_stamford.id, self.body_canopy.id},
        )
        self.assertEqual(production.lot_producing_id.name, production.name)
        card = production.x4u_generator_id
        self.assertTrue(card)
        self.assertEqual(card.x4u_enclosure, "Canopy")
        self.assertEqual(card.alternator_brand_id.name, "Stamford")
        self.assertEqual(card.sale_order_id, order)
        self.assertEqual(card.customer_id, self.customer)

    # T2: one material request for the Job Order, approved on its own
    def test_material_request(self):
        _order, production = self._sell()
        requests = production._x4u_purchase_requests()
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests.state, "approved")
        self.assertEqual(len(requests.line_ids), 3)
        self.assertIn(production.name, requests.origin or "")
        events = production.x4u_event_ids.mapped("event_type")
        for event in ("order_opened", "job_order_created", "material_request"):
            self.assertIn(event, events)
        self.assertEqual(set(production.move_raw_ids.mapped("x4u_part_status")), {"requested"})

    # T3 + T4 + T7: purchasing picks vendors, GM approves, then the whole cycle
    def test_full_cycle(self):
        order, production = self._sell()
        orders = self._order_parts(production)
        self.assertEqual(len(orders), 2)
        for po in orders:
            self.assertIn(production.name, po.origin or "")
        engine = production.move_raw_ids.filtered(lambda m: m.x4u_role == "engine")
        self.assertEqual(engine.x4u_part_status, "rfq")
        orders.with_user(self.buyer).button_confirm()
        self.assertEqual(set(orders.mapped("state")), {"to approve"})
        orders.with_user(self.manager).button_approve()
        engine.invalidate_recordset()
        self.assertEqual(engine.x4u_part_status, "ordered")
        self.assertEqual(engine.x4u_vendor_id, self.vendor_engine)
        for picking in orders.picking_ids:
            self._validate(picking)
        self.assertEqual(production.x4u_job_state, "parts_ready")
        self._deliver_material(production)
        self.assertEqual(production.x4u_job_state, "material_delivered")
        self._produce(production)
        self.assertEqual(production.state, "done")
        self.assertEqual(production.x4u_job_state, "assembled")
        self._inspect(production, "success")
        self._deliver(order)
        self.assertEqual(production.x4u_job_state, "finished")
        self.assertEqual(production.x4u_generator_id.state, "delivered")
        events = production.x4u_event_ids.mapped("event_type")
        for event in ("rfq_created", "po_approved", "part_received", "parts_ready", "material_delivered", "assembled", "qc_passed", "delivered"):
            self.assertIn(event, events)
        self.assertEqual(events.count("rfq_created"), 2)
        self.assertEqual(events.count("po_approved"), 2)
        self.assertEqual(events.count("part_received"), 3)

    # T5: a part already in stock is used and not requested
    def test_part_taken_from_stock(self):
        self.env["stock.quant"]._update_available_quantity(self.engine, self.warehouse.lot_stock_id, 1)
        _order, production = self._sell()
        engine = production.move_raw_ids.filtered(lambda m: m.x4u_role == "engine")
        self.assertEqual(engine.x4u_part_status, "from_stock")
        self.assertEqual(len(production._x4u_purchase_requests().line_ids), 2)

    # T7: nobody can change or delete the timeline
    def test_events_cannot_be_changed(self):
        _order, production = self._sell()
        event = production.x4u_event_ids[:1]
        with self.assertRaises(UserError):
            event.with_user(self.manager).write({"detail": "changed"})
        with self.assertRaises(UserError):
            event.with_user(self.manager).unlink()

    # T8: days per stage and where the delay is
    def test_durations_and_delay(self):
        _order, production = self._sell()
        Event = self.env["x4u.job.order.event"].sudo()
        production.x4u_event_ids.sudo().unlink()
        start = fields.Datetime.now() - timedelta(days=20)
        for days, event in ((0, "order_opened"), (0, "material_request"), (2, "rfq_created"), (3, "po_approved"), (10, "parts_ready")):
            Event.create({"production_id": production.id, "event_type": event, "date": start + timedelta(days=days)})
        self.assertAlmostEqual(production.x4u_days_purchasing, 2.0)
        self.assertAlmostEqual(production.x4u_days_approval, 1.0)
        self.assertAlmostEqual(production.x4u_days_supplier, 7.0)
        self.assertFalse(production.x4u_delay_stage)
        self.env["ir.config_parameter"].sudo().set_param("x4u_job_order.target_supplier_days", 5)
        self.env["mrp.production"]._cron_x4u_update_delays()
        self.assertEqual(production.x4u_delay_stage, "supplier")
        self.assertAlmostEqual(production.x4u_delay_days, 2.0)

    # T9: late Job Orders
    def test_late(self):
        _order, production = self._sell()
        production.date_deadline = fields.Datetime.now() - timedelta(days=1)
        late = self.env["mrp.production"].search(
            [
                ("id", "=", production.id),
                ("date_deadline", "<", fields.Date.today()),
                ("x4u_job_state", "not in", ("finished", "cancelled")),
            ]
        )
        self.assertEqual(late, production)

    # T10: sales can read the Job Order and its timeline
    def test_salesman_reads_job_order(self):
        _order, production = self._sell()
        job = production.with_user(self.salesman)
        job.read(["name", "x4u_job_state", "x4u_engine_status", "x4u_delay_stage"])
        job.x4u_event_ids.read(["event_type", "date", "user_id"])

    # T11: Purchasing and Quality open the Job Order they are told about, read only (guide R1)
    def test_purchasing_and_quality_read_job_order(self):
        viewer = "x4u_job_order.group_x4u_job_order_viewer"
        buyer = new_test_user(
            self.env,
            login="x4u_jo_viewer_buyer",
            groups="base.group_user,purchase.group_purchase_user,purchase_request.group_purchase_request_manager," + viewer,
        )
        inspector = new_test_user(
            self.env, login="x4u_jo_viewer_qc", groups="base.group_user,quality_control_oca.group_quality_control_user," + viewer
        )
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("x4u_job_order.purchase_user_id", buyer.id)
        params.set_param("x4u_job_order.qc_user_id", inspector.id)
        _order, production = self._sell()
        orders = self._order_parts(production)
        orders.with_user(self.manager).button_confirm()
        for picking in orders.picking_ids:
            self._validate(picking)
        self._deliver_material(production)
        self._produce(production)
        self._inspect(production, "success")
        list_views = [
            (self.env.ref("x4u_job_order.x4u_job_order_view_list").id, "list"),
            (self.env.ref("x4u_job_order.x4u_job_order_view_kanban").id, "kanban"),
        ]
        for user, menu in ((buyer, "menu_x4u_job_order_purchase"), (inspector, "menu_x4u_job_order_quality")):
            job = production.with_user(user)
            self.assertTrue(job.activity_ids.filtered(lambda a, u=user: a.user_id == u))
            # The list, the kanban and the form load like in the browser, with no access error.
            fields_ = job.get_views(list_views)["models"]["mrp.production"]["fields"]
            spec = {name: {"fields": {"display_name": {}}} if job._fields[name].type == "many2one" else {} for name in fields_}
            self.assertEqual(job.web_search_read([("id", "=", production.id)], spec)["length"], 1)
            Form(job)
            job.x4u_event_ids.read(["event_type", "document", "user_id"])
            self.assertIn(self.env.ref("x4u_job_order." + menu).id, self.env["ir.ui.menu"].with_user(user)._visible_menu_ids())
            with self.assertRaises(AccessError):
                job.write({"origin": "changed"})
