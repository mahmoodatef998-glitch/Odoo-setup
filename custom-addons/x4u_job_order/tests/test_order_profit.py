from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import X4uJobOrderCommon


@tagged("post_install", "-at_install")
class TestOrderProfit(X4uJobOrderCommon):
    """Spec v0.14: the overhead of a Job Order (H1) and the profitability of the order (H2-H5)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.accountant = new_test_user(
            cls.env, login="x4u_jo_profit_accountant", groups="base.group_user,account.group_account_invoice"
        )
        cls.pricelist = cls.env["product.pricelist"].create(
            {"name": "X4U Test Profit", "currency_id": cls.env.company.currency_id.id}
        )

    def _sell_one(self):
        """One generator sold at 10,000 before VAT; its parts in stock at 1,000 (engine), 500 and 300."""
        self.template.categ_id = self.env.ref("x4u_setup_base.categ_generators")
        for part, price in ((self.engine, 1000.0), (self.alt_stamford, 500.0), (self.body_canopy, 300.0)):
            self._stock(part, 1, price=price)
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "warehouse_id": self.warehouse.id,
                "pricelist_id": self.pricelist.id,
                "order_line": [Command.create({"product_id": self.variant.id, "product_uom_qty": 1, "price_unit": 10000.0})],
            }
        )
        order.action_confirm()
        job = order.x4u_job_ids
        return order, job, job.production_ids

    # T50 (H1): the Accountant changes the overhead of one Job Order; its generator takes it
    def test_overhead_of_the_job_order(self):
        rate = float(self.env["ir.config_parameter"].sudo().get_param("x4u_job_order.overhead_percent") or 0.0)
        _order, job, production = self._sell_one()
        self.assertEqual(job.overhead_percent, rate, "the general rate by default")
        with self.assertRaises(UserError):
            job.with_user(self.operation).write({"overhead_percent": 25.0})
        job.with_user(self.accountant).write({"overhead_percent": 25.0})
        self._deliver_materials(production)
        self._finish(production)
        self.assertAlmostEqual(production.extra_cost * production.qty_produced, 1800.0 * 0.25)
        with self.assertRaises(UserError):
            job.with_user(self.accountant).write({"overhead_percent": 30.0})

    # T51 (H2-H5): a finished generator by its serials, a transport bill on the Job Order, the profit
    def test_order_profitability(self):
        _order, job, production = self._sell_one()
        self._deliver_materials(production)
        self._finish(production)
        sheet = job._x4u_cost_sheet_values()
        row = sheet["generators"][0]
        parts = {part["label"]: part for part in row["parts"]}
        engine = production.x4u_engine_lot_id
        self.assertEqual((parts["Engine"]["serial"], parts["Engine"]["cost"]), (engine.name, 1000.0))
        self.assertEqual(parts["Alternator"]["cost"], 500.0)
        self.assertEqual((parts["Canopy"]["serial"], parts["Canopy"]["cost"]), (production.x4u_body_lot_id.name, 300.0))
        self.assertEqual((row["status"], row["serial"]), ("actual", engine.name))
        self.assertAlmostEqual(row["materials"], 1800.0)
        self.assertAlmostEqual(row["overhead"], 1800.0 * job.overhead_percent / 100)
        self.assertAlmostEqual(row["price"], 10000.0)
        cost = 1800.0 * (1 + job.overhead_percent / 100)
        self.assertAlmostEqual(job.x4u_cost, cost, msg="H5: the figures follow the finish")
        # A transport bill on the Job Order's analytic account is a direct cost.
        expense = self.env["account.account"].search(
            [("account_type", "=", "expense"), *self.env["account.account"]._check_company_domain(self.env.company)], limit=1
        )
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor_aqt.id,
                "invoice_date": production.date_finished.date(),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Transport to site",
                            "account_id": expense.id,
                            "price_unit": 200.0,
                            "tax_ids": [Command.clear()],
                            "analytic_distribution": {str(job.analytic_account_id.id): 100.0},
                        }
                    )
                ],
            }
        )
        bill.action_post()
        self.assertAlmostEqual(job.x4u_direct_cost, 200.0)
        self.assertAlmostEqual(job.x4u_profit, 10000.0 - cost - 200.0)
        self.assertEqual(job.x4u_profit_status, "estimated", "no tax invoice yet")
        html = self.env["ir.actions.report"]._render_qweb_html("x4u_job_order.action_report_cost_sheet", job.ids)[0]
        for text in (engine.name, production.x4u_body_lot_id.name, bill.name, "Overhead", "Direct costs"):
            self.assertIn(text.encode(), html, text)
        self.assertIn(engine.name, job.with_user(self.accountant).x4u_cost_sheet, "the Profitability tab")
        self.assertFalse(job.with_user(self.operation).x4u_cost_sheet, "for Accounting only")

    # T52 (H2): a generator not finished: estimated with the serials chosen for it
    def test_estimated_with_the_serials_chosen(self):
        _order, job, production = self._sell_one()
        engine = self._lots(self.engine)
        production.with_user(self.operation).write({"x4u_engine_lot_id": engine.id})
        row = job._x4u_cost_sheet_values()["generators"][0]
        parts = {part["label"]: part for part in row["parts"]}
        self.assertEqual(row["status"], "estimated")
        self.assertEqual((parts["Engine"]["serial"], parts["Engine"]["cost"]), (engine.name, 1000.0))
        self.assertAlmostEqual(row["materials"], 1800.0)
        self.assertAlmostEqual(row["cost"], 1800.0 * (1 + job.overhead_percent / 100))
