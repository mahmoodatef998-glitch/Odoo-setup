from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, new_test_user, tagged

from .common import X4uJobOrderCommon


@tagged("post_install", "-at_install")
class TestJobOrder(X4uJobOrderCommon):
    # T1 + T6: the sale opens the Job Order with the parts of the variant sold
    def test_sale_opens_job_order(self):
        order, production = self._sell()
        self.assertEqual(len(production), 1)
        self.assertRegex(production.name, r"^MO\d{3,}$")
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
        self.assertEqual(production.x4u_job_state, "finished")
        # No inspection: the generator goes to the customer straight away (v0.4 V7).
        self._deliver(order)
        self.assertEqual(production.x4u_job_state, "delivered")
        self.assertEqual(production.x4u_generator_id.state, "delivered")
        events = production.x4u_event_ids.mapped("event_type")
        for event in ("rfq_created", "po_approved", "part_received", "parts_ready", "material_delivered", "finished", "delivered"):
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
                ("x4u_job_state", "not in", ("delivered", "cancelled")),
            ]
        )
        self.assertEqual(late, production)

    # T10: sales can read the Job Order and its timeline
    def test_salesman_reads_job_order(self):
        _order, production = self._sell()
        job = production.with_user(self.salesman)
        job.read(["name", "x4u_job_state", "x4u_engine_status", "x4u_delay_stage"])
        job.x4u_event_ids.read(["event_type", "date", "user_id"])

    # T11: Purchasing, Quality and the Storekeeper open the Job Orders read only (guide R1, v0.4)
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
        params.set_param("x4u_job_order.warehouse_user_id", self.storekeeper.id)
        _order, production = self._sell()
        orders = self._order_parts(production)
        orders.with_user(self.manager).button_confirm()
        for picking in orders.picking_ids:
            self._validate(picking)
        self._deliver_material(production)
        self._produce(production)
        list_views = [
            (self.env.ref("x4u_job_order.x4u_job_order_view_list").id, "list"),
            (self.env.ref("x4u_job_order.x4u_job_order_view_kanban").id, "kanban"),
        ]
        for user, menu, told in (
            (buyer, "menu_x4u_job_order_purchase", True),
            (inspector, "menu_x4u_job_order_quality", False),
            (self.storekeeper, "menu_x4u_job_order_inventory", True),
        ):
            job = production.with_user(user)
            self.assertEqual(bool(job.activity_ids.filtered(lambda a, u=user: a.user_id == u)), told)
            # The list, the kanban and the form load like in the browser, with no access error.
            fields_ = job.get_views(list_views)["models"]["mrp.production"]["fields"]
            spec = {name: {"fields": {"display_name": {}}} if job._fields[name].type == "many2one" else {} for name in fields_}
            self.assertEqual(job.web_search_read([("id", "=", production.id)], spec)["length"], 1)
            Form(job)
            job.x4u_event_ids.read(["event_type", "document", "user_id"])
            self.assertIn(self.env.ref("x4u_job_order." + menu).id, self.env["ir.ui.menu"].with_user(user)._visible_menu_ids())
            with self.assertRaises(AccessError):
                job.write({"origin": "changed"})

    # T12: each part shows what the warehouse holds, and what is still free to use
    def test_parts_show_stock(self):
        self.env["stock.quant"]._update_available_quantity(self.engine, self.warehouse.lot_stock_id, 2)
        _order, production = self._sell()
        engine = production.move_raw_ids.filtered(lambda m: m.x4u_role == "engine")
        body = production.move_raw_ids.filtered(lambda m: m.x4u_role == "body")
        # One engine is reserved for this Job Order by Pick Components, one is still free.
        self.assertEqual((engine.x4u_stock_on_hand, engine.x4u_stock_free), (2.0, 1.0))
        self.assertEqual((body.x4u_stock_on_hand, body.x4u_stock_free), (0.0, 0.0))

    # T13: no Produce before the Storekeeper delivers the parts to the factory
    def test_produce_needs_parts_in_factory(self):
        for part in (self.engine, self.alt_stamford, self.body_canopy):
            self.env["stock.quant"]._update_available_quantity(part, self.warehouse.lot_stock_id, 1)
        _order, production = self._sell()
        self.assertEqual(production.x4u_job_state, "parts_ready")
        # assertRaises (not assertRaisesRegex) undoes the refused try, like the browser does.
        with self.assertRaises(UserError) as refused:
            self._produce(production)
        self.assertIn("Deliver Materials", str(refused.exception))
        self.assertNotEqual(production.state, "done")
        self._deliver_material(production)
        self._produce(production)
        self.assertEqual(production.state, "done")
        pre_production = production.move_raw_ids.location_id
        self.assertFalse(
            self.env["stock.quant"].search([("location_id", "in", pre_production.ids), ("quantity", "<", 0)])
        )

    # T14: a sale of 2 generators opens 2 Job Orders, each with its own serial and parts (v0.4 V8)
    def test_one_job_order_per_generator(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "warehouse_id": self.warehouse.id,
                "order_line": [Command.create({"product_id": self.variant.id, "product_uom_qty": 2})],
            }
        )
        order.action_confirm()
        productions = order.mrp_production_ids
        self.assertEqual(len(productions), 2)
        self.assertEqual(productions.mapped("product_qty"), [1.0, 1.0])
        for production in productions:
            self.assertEqual(production.lot_producing_id.name, production.name)
            self.assertEqual(production.x4u_generator_id.sale_order_id, order)
            self.assertEqual(len(production._x4u_purchase_requests()), 1)
            self.assertEqual(len(production._x4u_pick_components()), 1)
            self.assertEqual(production.x4u_material_flag, "missing")

    # T14b: a Job Order made in two goes (opened by hand for 2): the second serial is its own number
    def test_backorder_keeps_job_order_number(self):
        for part in (self.engine, self.alt_stamford, self.body_canopy):
            self.env["stock.quant"]._update_available_quantity(part, self.warehouse.lot_stock_id, 2)
        production = self.env["mrp.production"].create({"product_id": self.variant.id, "product_qty": 2})
        production.action_confirm()
        self._deliver_material(production)
        # The first generator: Production consumes one set of parts and keeps a backorder.
        with Form(production) as form:
            form.qty_producing = 1
        for move in production.move_raw_ids:
            move.quantity = move.should_consume_qty
        production.move_raw_ids.picked = True
        action = production.button_mark_done()
        self.assertEqual(action["res_model"], "mrp.production.backorder")
        Form(self.env[action["res_model"]].with_context(**action["context"])).save().action_backorder()
        self.assertEqual(production.state, "done")
        backorder = production.procurement_group_id.mrp_production_ids - production
        self.assertEqual(len(backorder), 1)
        if not backorder.lot_producing_id:
            backorder.action_generate_serial()
        self.assertEqual(backorder.lot_producing_id.name, backorder.name)
        self._produce(backorder)
        self.assertEqual(backorder.state, "done")

    # T15: red flag while a part is missing, green once every part is reserved (v0.4 V2)
    def test_flag_red_then_green(self):
        _order, production = self._sell()
        self.assertEqual(production.x4u_material_flag, "missing")
        self.assertIn(production, self.env["mrp.production"].search([("x4u_material_flag", "=", "missing")]))
        for part in (self.engine, self.alt_stamford, self.body_canopy):
            self.env["stock.quant"]._update_available_quantity(part, self.warehouse.lot_stock_id, 1)
        production._x4u_pick_components().action_assign()
        self.assertEqual(production.x4u_job_state, "parts_ready")
        self.assertEqual(production.x4u_material_flag, "ready")

    # T16: the Storekeeper delivers the materials from the Job Order, in two goes (v0.4 V3)
    def test_deliver_materials(self):
        for part in (self.engine, self.alt_stamford, self.body_canopy):
            self.env["stock.quant"]._update_available_quantity(part, self.warehouse.lot_stock_id, 1)
        _order, production = self._sell()
        with self.assertRaises(UserError):
            self._deliver_materials(production, {self.engine: 2})
        self._deliver_materials(production, {self.engine: 1})
        self.assertEqual(production.x4u_job_state, "parts_ready")
        stock = self.warehouse.lot_stock_id
        self.assertEqual(self.engine.with_context(location=stock.id).qty_available, 0)
        self.assertEqual(self.body_canopy.with_context(location=stock.id).qty_available, 1)
        self._deliver_materials(production)
        self.assertEqual(production.x4u_job_state, "material_delivered")
        self.assertFalse(production._x4u_pick_components())
        self.assertEqual(self.body_canopy.with_context(location=stock.id).qty_available, 0)

    # T17: the Operation Manager finishes the Job Order; the generator is worth its parts + 20% (v0.4 V4 / V5)
    def test_finish_job_order_values_the_generator(self):
        # Generators and their parts are FIFO (set on install); the test generator joins its category.
        self.template.categ_id = self.env.ref("x4u_setup_base.categ_generators")
        self.assertEqual(self.template.cost_method, "fifo")
        self.assertEqual(self.engine.cost_method, "fifo")
        stock = self.warehouse.lot_stock_id
        for part, price in ((self.engine, 1000.0), (self.alt_stamford, 500.0), (self.body_canopy, 300.0)):
            part.standard_price = price
            self.env["stock.quant"].with_context(inventory_mode=True).create(
                {"product_id": part.id, "location_id": stock.id, "inventory_quantity": 1}
            ).action_apply_inventory()
        _order, production = self._sell()
        with self.assertRaises(UserError):
            production.with_user(self.operation).action_x4u_finish()
        self._deliver_materials(production)
        production.with_user(self.operation).action_x4u_finish()
        self.assertEqual(production.state, "done")
        self.assertEqual(production.x4u_job_state, "finished")
        self.assertTrue(self.template.lot_valuated)
        finished = production.move_finished_ids.filtered(lambda m: m.product_id == production.product_id)
        self.assertAlmostEqual(sum(finished.stock_valuation_layer_ids.mapped("value")), 1800.0 * 1.2)
        self.assertEqual(finished.stock_valuation_layer_ids.lot_id, production.lot_producing_id)
