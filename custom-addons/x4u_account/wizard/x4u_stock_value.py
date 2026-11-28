from collections import defaultdict
from datetime import datetime, time

import pytz

from odoo import _, api, fields, models


class X4uStockValue(models.TransientModel):
    """Spec §23: the value of the stock on a date, by category and product, each serial at its own
    cost, against the balance of the stock accounts in the books (the accountant ticks they agree).

    Built from the valuation layers (stock.valuation.layer) up to the end of the date, so it is the
    same number the stock journal entries posted."""

    _name = "x4u.stock.value"
    _description = "Stock Value"

    date = fields.Date(required=True, default=fields.Date.context_today, string="On")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    line_ids = fields.One2many("x4u.stock.value.line", "wizard_id", string="Products")
    account_ids = fields.One2many("x4u.stock.value.account", "wizard_id", string="Stock Accounts")
    total_value = fields.Monetary("Stock Value", readonly=True)
    book_balance = fields.Monetary("Book Balance (134xxx)", readonly=True)
    difference = fields.Monetary(readonly=True, help="Stock value minus the book balance: 0 when they agree.")
    computed = fields.Boolean(readonly=True)

    @api.depends("date")
    def _compute_display_name(self):
        for wizard in self:
            wizard.display_name = _("Stock Value on %s", fields.Date.to_string(wizard.date)) if wizard.date else _("Stock Value")

    def _x4u_until(self):
        """The end of the date in the user's time zone, in UTC like create_date."""
        tz = pytz.timezone(self.env.user.tz or "Asia/Dubai")
        end = tz.localize(datetime.combine(self.date, time.max))
        return end.astimezone(pytz.utc).replace(tzinfo=None)

    def _x4u_layers(self):
        """(product, lot) -> [quantity, value] of the layers up to the date."""
        self.env["stock.valuation.layer"].flush_model()
        self.env.cr.execute(
            """
            SELECT product_id, lot_id, SUM(quantity), SUM(value)
              FROM stock_valuation_layer
             WHERE company_id = %s AND create_date <= %s
          GROUP BY product_id, lot_id
            """,
            (self.company_id.id, self._x4u_until()),
        )
        return self.env.cr.fetchall()

    def _x4u_compute(self):
        self.ensure_one()
        currency = self.currency_id
        rounding = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        per_product = defaultdict(lambda: {"qty": 0.0, "value": 0.0, "lots": []})
        for product_id, lot_id, qty, value in self._x4u_layers():
            data = per_product[product_id]
            data["qty"] += qty or 0.0
            data["value"] += value or 0.0
            if round(qty or 0.0, rounding) or not currency.is_zero(value or 0.0):
                data["lots"].append((lot_id, qty or 0.0, value or 0.0))
        Product = self.env["product.product"].with_context(active_test=False)
        lines = []
        for product_id, data in per_product.items():
            if not round(data["qty"], rounding) and currency.is_zero(data["value"]):
                continue
            product = Product.browse(product_id)
            # Valued by serial (engine, CKD, body, generator): a line per serial at its own cost.
            # Valued at the average (spare parts): no serial lines, the product line is enough.
            serials = [
                {"lot_id": lot_id, "quantity": qty, "value": currency.round(value)}
                for lot_id, qty, value in data["lots"]
                if lot_id
            ]
            lines.append(
                {
                    "product_id": product_id,
                    "categ_id": product.categ_id.id,
                    "quantity": data["qty"],
                    "value": currency.round(data["value"]),
                    "serial_count": len([s for s in serials if round(s["quantity"], rounding) > 0]),
                    "lot_ids": [(0, 0, s) for s in serials],
                }
            )
        self.line_ids.unlink()
        self.account_ids.unlink()
        self.write({"line_ids": [(0, 0, vals) for vals in lines]})
        self._x4u_compute_books()

    def _x4u_compute_books(self):
        """The stock accounts of the categories in stock or with a balance, against their stock value."""
        currency = self.currency_id
        company = self.company_id
        Category = self.env["product.category"].sudo().with_company(company)
        categories = Category.search([])
        value_by_account = defaultdict(float)
        for line in self.line_ids:
            account = line.categ_id.sudo().with_company(company).property_stock_valuation_account_id
            value_by_account[account.id] += line.value
        accounts = categories.mapped("property_stock_valuation_account_id") | self.env["account.account"].sudo().browse(
            [account_id for account_id in value_by_account if account_id]
        )
        balances = {}
        if accounts:
            # The Storekeeper sees the total of the books, not the entries: read with full rights.
            groups = self.env["account.move.line"].sudo()._read_group(
                [
                    ("account_id", "in", accounts.ids),
                    ("company_id", "=", company.id),
                    ("parent_state", "=", "posted"),
                    ("date", "<=", self.date),
                ],
                ["account_id"],
                ["balance:sum"],
            )
            balances = {account.id: balance for account, balance in groups}
        rows = []
        for account in accounts.sorted("code"):
            stock_value = currency.round(value_by_account.get(account.id, 0.0))
            book = currency.round(balances.get(account.id, 0.0))
            if currency.is_zero(stock_value) and currency.is_zero(book):
                continue
            rows.append({"account_id": account.id, "stock_value": stock_value, "book_balance": book,
                         "difference": currency.round(stock_value - book)})
        unvalued = currency.round(value_by_account.get(False, 0.0))
        if not currency.is_zero(unvalued):
            rows.append({"account_id": False, "stock_value": unvalued, "book_balance": 0.0, "difference": unvalued})
        total = currency.round(sum(self.line_ids.mapped("value")))
        book = currency.round(sum(row["book_balance"] for row in rows))
        self.write(
            {
                "account_ids": [(0, 0, row) for row in rows],
                "total_value": total,
                "book_balance": book,
                "difference": currency.round(total - book),
                "computed": True,
            }
        )

    def action_view(self):
        self._x4u_compute()
        return {
            "type": "ir.actions.act_window",
            "name": _("Stock Value on %s", fields.Date.to_string(self.date)),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "views": [(self.env.ref("x4u_account.x4u_stock_value_view_result").id, "form")],
            "target": "current",
        }

    def action_open_products(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Stock Value on %s", fields.Date.to_string(self.date)),
            "res_model": "x4u.stock.value.line",
            "view_mode": "list,form",
            "domain": [("wizard_id", "=", self.id)],
            "context": {"group_by": ["categ_id"], "create": False, "edit": False, "delete": False},
        }

    def action_export_xlsx(self):
        if not self.computed:
            self._x4u_compute()
        return self.env.ref("x4u_account.action_report_x4u_stock_value_xlsx").report_action(self)


class X4uStockValueLine(models.TransientModel):
    _name = "x4u.stock.value.line"
    _description = "Stock Value - Product"
    _order = "categ_id, product_id"

    wizard_id = fields.Many2one("x4u.stock.value", required=True, ondelete="cascade", index=True)
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    categ_id = fields.Many2one("product.category", string="Category", readonly=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    uom_id = fields.Many2one(related="product_id.uom_id")
    quantity = fields.Float(digits="Product Unit of Measure", readonly=True, aggregator="sum")
    unit_cost = fields.Monetary("Average Unit Cost", compute="_compute_unit_cost", aggregator=None)
    value = fields.Monetary("Total Value", readonly=True, aggregator="sum")
    serial_count = fields.Integer("Serials", readonly=True, aggregator="sum")
    lot_ids = fields.One2many("x4u.stock.value.lot", "line_id", string="Serials")

    @api.depends("quantity", "value")
    def _compute_unit_cost(self):
        for line in self:
            line.unit_cost = line.value / line.quantity if line.quantity else 0.0


class X4uStockValueLot(models.TransientModel):
    _name = "x4u.stock.value.lot"
    _description = "Stock Value - Serial"
    _order = "lot_id"

    line_id = fields.Many2one("x4u.stock.value.line", required=True, ondelete="cascade", index=True)
    currency_id = fields.Many2one(related="line_id.currency_id")
    lot_id = fields.Many2one("stock.lot", string="Serial", readonly=True)
    quantity = fields.Float(digits="Product Unit of Measure", readonly=True)
    value = fields.Monetary("Cost", readonly=True)


class X4uStockValueAccount(models.TransientModel):
    _name = "x4u.stock.value.account"
    _description = "Stock Value - Stock Account"

    wizard_id = fields.Many2one("x4u.stock.value", required=True, ondelete="cascade", index=True)
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    account_id = fields.Many2one("account.account", string="Account", readonly=True)
    stock_value = fields.Monetary(readonly=True)
    book_balance = fields.Monetary(readonly=True)
    difference = fields.Monetary(readonly=True)
