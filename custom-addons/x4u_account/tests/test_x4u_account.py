from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestX4uAccount(TransactionCase):
    """x4u_account spec: the menus and the PDC cheque cycle (issued, cleared, bounced)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Journal = cls.env["account.journal"]
        cls.bank = Journal.search([("type", "=", "bank"), *Journal._check_company_domain(cls.company)], limit=1)
        cls.misc = Journal.search([("type", "=", "general"), *Journal._check_company_domain(cls.company)], limit=1)
        cls.pdc_line = cls.bank.outbound_payment_method_line_ids.filtered(lambda line: line.code == "x4u_pdc")
        cls.pdc_account = cls.company._x4u_pdc_issued_account()
        cls.vendor = cls.env["res.partner"].create({"name": "X4U Test PDC Vendor"})

    def _bill(self, amount=1000.0):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    Command.create(
                        {"name": "X4U Test Service", "quantity": 1, "price_unit": amount, "tax_ids": [Command.clear()]}
                    )
                ],
            }
        )
        bill.action_post()
        return bill

    def _pay_by_pdc(self, bill, number):
        return (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=bill.ids)
            .create(
                {
                    "journal_id": self.bank.id,
                    "payment_method_line_id": self.pdc_line.id,
                    "x4u_cheque_number": number,
                    "x4u_cheque_date": fields.Date.add(fields.Date.today(), days=30),
                }
            )
            ._create_payments()
        )

    def _clear(self, payment):
        """What the bank reconciliation does when the bank pays the cheque: it matches the PDC line."""
        clearing = self.env["account.move"].create(
            {
                "journal_id": self.misc.id,
                "date": payment.x4u_cheque_date,
                "line_ids": [
                    Command.create(
                        {"account_id": self.pdc_account.id, "debit": payment.amount, "partner_id": self.vendor.id}
                    ),
                    Command.create({"account_id": self.bank.default_account_id.id, "credit": payment.amount}),
                ],
            }
        )
        clearing.action_post()
        liquidity = payment._seek_for_lines()[0]
        (liquidity + clearing.line_ids.filtered(lambda line: line.account_id == self.pdc_account)).reconcile()

    def test_menus(self):
        self.assertEqual(
            self.env.ref("account_asset_management.menu_finance_assets").parent_id,
            self.env.ref("account.menu_finance_entries"),
        )
        for xmlid in ("account.product_product_menu_sellable", "account.product_product_menu_purchasable"):
            self.assertFalse(self.env.ref(xmlid).active, xmlid)
        bills = self.env.ref("account.menu_action_move_in_invoice_type").with_context(lang="en_US")
        self.assertEqual(bills.name, "Invoices")
        self.assertEqual(self.env.ref("x4u_account.menu_x4u_pdc").parent_id, self.env.ref("account.menu_finance_payables"))

    def test_pdc_issued_then_cleared(self):
        self.assertTrue(self.pdc_line, "Every bank journal has a PDC Cheque line.")
        self.assertEqual(self.pdc_account.account_type, "liability_current")
        bill = self._bill()
        payment = self._pay_by_pdc(bill, "000123")
        self.assertEqual(payment.x4u_cheque_number, "000123")
        self.assertEqual(payment.x4u_pdc_state, "issued")
        self.assertEqual(payment.outstanding_account_id, self.pdc_account)
        # P8: In Payment until the bank pays the cheque (Community would say Paid at once).
        self.assertEqual(bill.payment_state, "in_payment")
        self.assertIn("000123", payment._seek_for_lines()[0].name)
        self._clear(payment)
        self.assertEqual(payment.x4u_pdc_state, "cleared")
        self.assertEqual(bill.payment_state, "paid")
        with self.assertRaises(UserError):
            payment._x4u_pdc_bounce("Too late")

    def test_bounce_reopens_the_bill(self):
        bill = self._bill()
        payment = self._pay_by_pdc(bill, "000124")
        self.env["x4u.pdc.bounce"].create({"payment_id": payment.id, "reason": "Insufficient funds"}).action_confirm()
        self.assertEqual(payment.x4u_pdc_state, "bounced")
        self.assertEqual(payment.state, "canceled")
        self.assertEqual(payment.x4u_pdc_bounce_reason, "Insufficient funds")
        self.assertEqual(bill.payment_state, "not_paid")
        # The same cheque number can be written again on a new cheque.
        self.assertEqual(self._pay_by_pdc(bill, "000124").x4u_pdc_state, "issued")

    def test_cheque_number_and_date_required(self):
        vals = {
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": self.vendor.id,
            "amount": 500.0,
            "journal_id": self.bank.id,
            "payment_method_line_id": self.pdc_line.id,
        }
        payment = self.env["account.payment"].create(vals)
        with self.assertRaises(UserError):
            payment.action_post()
        payment.write({"x4u_cheque_number": "000125", "x4u_cheque_date": fields.Date.today()})
        payment.action_post()
        self.assertEqual(payment.x4u_pdc_state, "issued")
        twin = self.env["account.payment"].create(
            dict(vals, x4u_cheque_number="000125", x4u_cheque_date=fields.Date.today())
        )
        with self.assertRaises(UserError):
            twin.action_post()

    def test_menus_v11(self):
        journal_items = self.env.ref("account.menu_action_account_moves_all")
        self.assertEqual(journal_items.groups_id, self.env.ref("account.group_account_manager"))
        petty = self.env.ref("account_usability.menu_accounting_statement_cash").with_context(lang="en_US")
        self.assertEqual(petty.name, "Petty Cash")
        rp = self.env.ref("x4u_account.menu_x4u_receivable_payable")
        self.assertEqual(rp.parent_id, self.env.ref("account.menu_finance"))
        self.assertEqual(self.env.ref("account_due_list.menu_action_invoice_payments").parent_id, rp)
        self.assertEqual(len(rp.child_id), 7)

    def test_equity_and_petty_cash(self):
        Account = self.env["account.account"]
        for code in ("301001", "302001", "303001", "304001", "305001"):
            account = Account.search([("code", "=", code), *Account._check_company_domain(self.company)])
            self.assertEqual(account.account_type, "equity", code)
        Journal = self.env["account.journal"]
        cash = Journal.search([("type", "=", "cash"), *Journal._check_company_domain(self.company)])
        self.assertIn("Petty Cash", cash.with_context(lang="en_US").mapped("name"))

    def test_statement_groups(self):
        self.assertTrue(self.env.user.has_group("partner_statement.group_outstanding_statement"))

    def test_bank_statement_clears_the_cheque(self):
        """R1: the statement line with the cheque number reconciles by itself."""
        bill = self._bill(1200.0)
        payment = self._pay_by_pdc(bill, "000126")
        self.env["account.bank.statement.line"].with_context(_test_account_reconcile_oca=True).create(
            {
                "journal_id": self.bank.id,
                "date": payment.x4u_cheque_date,
                "amount": -1200.0,
                "partner_id": self.vendor.id,
                "payment_ref": "CHQ PAID Cheque 000126",
            }
        )
        self.assertEqual(payment.x4u_pdc_state, "cleared")
        self.assertEqual(bill.payment_state, "paid")

    def test_nightly_matching_by_reference(self):
        """R2: a payment meets its invoice when partner and reference are the same; otherwise it waits."""
        customer = self.env["res.partner"].create({"name": "X4U Test Customer"})
        invoices = self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "partner_id": customer.id,
                    "invoice_date": fields.Date.today(),
                    "invoice_line_ids": [
                        Command.create({"name": "X4U Test", "quantity": 1, "price_unit": 700.0, "tax_ids": [Command.clear()]})
                    ],
                }
                for _i in range(2)
            ]
        )
        invoices.action_post()
        manual = self.bank.inbound_payment_method_line_ids.filtered(lambda line: line.code == "manual")[:1]
        payments = self.env["account.payment"].create(
            [
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": customer.id,
                    "amount": 700.0,
                    "journal_id": self.bank.id,
                    "payment_method_line_id": manual.id,
                    "memo": memo,
                }
                for memo in (invoices[0].name, "no reference")
            ]
        )
        payments.action_post()
        receivable = customer.property_account_receivable_id
        task = self.env["account.mass.reconcile"].search([("account_id", "=", receivable.id)])
        self.assertTrue(task, "x4u_setup makes the nightly task for the receivable account")
        task.run_reconcile()
        self.assertIn(invoices[0].payment_state, ("paid", "in_payment"))
        self.assertEqual(invoices[1].payment_state, "not_paid", "same amount, no reference: left for the Accountant")

    def test_usd_peg(self):
        """Q1: an AED company gets USD at 3.6725 for every date, once."""
        from odoo.addons.x4u_account.hooks import _usd_peg

        company = self.env["res.company"].create({"name": "X4U Test AED Co", "currency_id": self.env.ref("base.AED").id})
        _usd_peg(self.env, company)
        _usd_peg(self.env, company)
        usd = self.env.ref("base.USD")
        rates = self.env["res.currency.rate"].search([("currency_id", "=", usd.id), ("company_id", "=", company.id)])
        self.assertEqual(len(rates), 1)
        amount = usd.with_company(company)._convert(100.0, company.currency_id, company, "2026-11-07")
        self.assertAlmostEqual(amount, 367.25, places=2)

    def test_account_fixes_and_categories(self):
        """Q2 / Q3 on accounts with the l10n_ae codes."""
        from odoo.addons.x4u_account import hooks

        Account = self.env["account.account"].with_company(self.company)

        def ensure(code, name, account_type):
            account = hooks._account(self.env, self.company, code)
            if account:
                return account
            return Account.create({"code": code, "name": name, "account_type": account_type})

        vat_payable = ensure("202003", "VAT Payable", "liability_payable")
        if not self.env["account.move.line"].search_count([("account_id", "=", vat_payable.id)]):
            vat_payable.account_type = "liability_payable"
        wip = ensure("106005", "Work In Progrees", "asset_current")
        wip.name = "Work In Progrees"
        ensure("500001", "Sales Account", "income")
        service = ensure("500008", "Service Income", "income")
        ensure("400001", "Cost of Goods Sold in Trading", "expense_direct_cost")
        office = ensure("400050", "Others - Office Various Expenses", "expense")
        services = self.env.ref("x4u_setup_base.categ_services").with_company(self.company)
        expenses = self.env.ref("product.cat_expense").with_company(self.company)
        Category = self.env["product.category"].with_company(self.company)
        services.property_account_income_categ_id = Category._fields[
            "property_account_income_categ_id"
        ].get_company_dependent_fallback(Category)
        expenses.property_account_expense_categ_id = Category._fields[
            "property_account_expense_categ_id"
        ].get_company_dependent_fallback(Category)
        hooks._fix_accounts(self.env, self.company)
        hooks._category_accounts(self.env, self.company)
        if not self.env["account.move.line"].search_count([("account_id", "=", vat_payable.id)]):
            self.assertEqual(vat_payable.account_type, "liability_current")
        self.assertEqual(wip.with_context(lang="en_US").name, "Work In Progress")
        self.assertTrue(hooks._account(self.env, self.company, "500015"), "Spare Parts Sales is created")
        self.assertEqual(services.property_account_income_categ_id, service)
        self.assertEqual(expenses.property_account_expense_categ_id, office)
        # The Accountant's own choice stays on the next upgrade.
        own = Account.create({"code": "500099", "name": "X4U Test Own Income", "account_type": "income"})
        services.property_account_income_categ_id = own
        hooks._category_accounts(self.env, self.company)
        self.assertEqual(services.property_account_income_categ_id, own)

    def _lines(self, moves):
        """{account code or name: balance} of the valuation entries of these stock moves."""
        result = {}
        for line in moves.stock_valuation_layer_ids.account_move_id.line_ids:
            key = line.account_id.code
            result[key] = result.get(key, 0.0) + line.balance
        return result

    def _name_serials(self, receipt):
        """With x4u_job_order every engine comes in with its serial (its spec v0.8 N1)."""
        for number, line in enumerate(receipt.move_line_ids, 1):
            if line.product_id.tracking == "serial" and not line.lot_name:
                line.lot_name = "X4U-ACC-%s-%s" % (receipt.id, number)

    def test_perpetual_inventory_cycle(self):
        """§9: receipt, MO with overhead, delivery and invoice each post their entry; WIP and GDNI close at zero."""
        from odoo.addons.x4u_account import hooks
        from odoo.tests import Form

        code = lambda c: hooks._account(self.env, self.company, c).code  # noqa: E731
        self.assertTrue(self.company.anglo_saxon_accounting)
        engines = self.env.ref("x4u_setup_base.categ_engines").with_company(self.company)
        generators = self.env.ref("x4u_setup_base.categ_generators").with_company(self.company)
        self.assertEqual(engines.property_valuation, "real_time")
        self.assertEqual(generators.property_stock_account_input_categ_id.code, code("201021"))
        part = self.env["product.product"].create(
            {"name": "X4U Test Engine", "is_storable": True, "categ_id": engines.id}
        )
        generator = self.env["product.product"].create(
            {"name": "X4U Test Genset", "is_storable": True, "categ_id": generators.id, "list_price": 5000.0}
        )
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": generator.product_tmpl_id.id,
                "product_qty": 1,
                "bom_line_ids": [Command.create({"product_id": part.id, "product_qty": 1})],
            }
        )
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        stock = warehouse.lot_stock_id
        mo = self.env["mrp.production"].create({"product_id": generator.id, "product_qty": 1, "bom_id": bom.id})
        mo.action_confirm()
        # 4U makes generators in 2 steps: the part is received straight where the MO takes it.
        components_location = mo.location_src_id

        # 1. Receipt: Dr Inventory - Components / Cr Goods Received Not Invoiced.
        receipt = self.env["stock.picking"].create(
            {
                "partner_id": self.vendor.id,
                "picking_type_id": warehouse.in_type_id.id,
                "location_id": self.env.ref("stock.stock_location_suppliers").id,
                "location_dest_id": components_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "name": part.name,
                            "product_id": part.id,
                            "product_uom_qty": 1,
                            "product_uom": part.uom_id.id,
                            "price_unit": 1000.0,
                            "location_id": self.env.ref("stock.stock_location_suppliers").id,
                            "location_dest_id": components_location.id,
                        }
                    )
                ],
            }
        )
        receipt.action_confirm()
        receipt.move_ids.quantity = 1
        self._name_serials(receipt)
        receipt.move_ids.picked = True
        receipt.button_validate()
        self.assertEqual(self._lines(receipt.move_ids), {code("103001"): 1000.0, code("201021"): -1000.0})

        # 2. MO with 200 overhead: Dr WIP / Cr Components, then Dr Finished / Cr WIP 1000 + Cr Applied Overhead 200.
        mo.action_assign()
        mo.extra_cost = 200.0
        mo_form = Form(mo)
        mo_form.qty_producing = 1
        mo = mo_form.save()
        mo.move_raw_ids.quantity = 1
        mo.move_raw_ids.picked = True
        mo.button_mark_done()
        self.assertEqual(mo.state, "done")
        lines = self._lines(mo.move_raw_ids | mo.move_finished_ids)
        self.assertEqual(lines.get(code("103001")), -1000.0)
        self.assertEqual(lines.get(code("103002")), 1200.0)
        self.assertEqual(lines.get(code("400072")), -200.0)
        self.assertFalse(lines.get(code("103004")), "WIP closes at zero")

        # 3. Delivery: Dr Goods Delivered Not Invoiced / Cr Inventory - Finished Generators.
        customer = self.env["res.partner"].create({"name": "X4U Test Genset Customer"})
        delivery = self.env["stock.picking"].create(
            {
                "partner_id": customer.id,
                "picking_type_id": warehouse.out_type_id.id,
                "location_id": stock.id,
                "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                "move_ids": [
                    Command.create(
                        {
                            "name": generator.name,
                            "product_id": generator.id,
                            "product_uom_qty": 1,
                            "product_uom": generator.uom_id.id,
                            "location_id": stock.id,
                            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                        }
                    )
                ],
            }
        )
        delivery.action_confirm()
        delivery.action_assign()
        delivery.move_ids.quantity = 1
        delivery.move_ids.picked = True
        delivery.button_validate()
        self.assertEqual(self._lines(delivery.move_ids), {code("103005"): 1200.0, code("103002"): -1200.0})

        # 4. Customer invoice (Anglo-Saxon): Dr Cost of Goods Sold / Cr Goods Delivered Not Invoiced.
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": customer.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    Command.create(
                        {"product_id": generator.id, "quantity": 1, "price_unit": 5000.0, "tax_ids": [Command.clear()]}
                    )
                ],
            }
        )
        invoice.action_post()
        cogs = invoice.line_ids.filtered(lambda line: line.display_type == "cogs")
        expense = generators.property_account_expense_categ_id
        self.assertEqual(sum(cogs.filtered(lambda line: line.account_id == expense).mapped("balance")), 1200.0)
        self.assertEqual(sum(cogs.filtered(lambda line: line.account_id.code == code("103005")).mapped("balance")), -1200.0)

    def test_switch_with_serial_valued_stock(self):
        """§9 S1: a periodic category with a serial-valued product in stock switches: Dr Inventory / Cr expense."""
        from odoo.addons.x4u_account import hooks

        Account = self.env["account.account"].with_company(self.company)
        category = self.env["product.category"].with_company(self.company).create({"name": "X4U Test Periodic"})
        category.write({"property_cost_method": "fifo", "property_valuation": "manual_periodic"})
        expense = category.property_account_expense_categ_id
        inventory = Account.create({"code": "199901", "name": "X4U Test Inventory", "account_type": "asset_current"})
        grni = hooks._account(self.env, self.company, "201021")
        gdni = hooks._account(self.env, self.company, "103005")
        wip = hooks._account(self.env, self.company, "103004")
        template = self.env["product.template"].create(
            {
                "name": "X4U Test Serial Genset",
                "is_storable": True,
                "tracking": "serial",
                "categ_id": category.id,
                "standard_price": 500.0,
            }
        )
        template.lot_valuated = True
        product = template.product_variant_id
        lot = self.env["stock.lot"].create({"name": "X4U-SN-0001", "product_id": product.id})
        stock = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1).lot_stock_id
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {"product_id": product.id, "location_id": stock.id, "lot_id": lot.id, "inventory_quantity": 1}
        ).action_apply_inventory()
        self.assertTrue(product.stock_valuation_layer_ids)
        hooks._switch_to_real_time(self.env, category, inventory, wip, grni, gdni)
        self.assertEqual(category.property_valuation, "real_time")
        self.assertTrue(template.lot_valuated, "serial valuation is back on")
        self.assertEqual(category.property_stock_account_input_categ_id, grni)
        self.assertEqual(category.property_stock_account_output_categ_id, gdni)
        lines = product.stock_valuation_layer_ids.account_move_id.line_ids
        self.assertEqual(sum(lines.filtered(lambda line: line.account_id == inventory).mapped("balance")), 500.0)
        self.assertEqual(sum(lines.filtered(lambda line: line.account_id == expense).mapped("balance")), -500.0)
        self.assertEqual(product.value_svl, 500.0)

    def test_landed_costs(self):
        """§10: the forwarder's freight goes into the engines' value; the clearing account closes at zero."""
        from odoo.addons.x4u_account import hooks

        freight = self.env.ref("x4u_account.product_landed_freight")
        clearing = hooks._account(self.env, self.company, "103018")
        self.assertTrue(freight.landed_cost_ok)
        self.assertEqual(freight.product_tmpl_id.get_product_accounts()["expense"], clearing)
        self.assertEqual(freight.product_tmpl_id.get_product_accounts()["stock_input"], clearing)
        self.assertFalse(self.env.ref("x4u_account.product_landed_customs").supplier_taxes_id)

        engines = self.env.ref("x4u_setup_base.categ_engines").with_company(self.company)
        part = self.env["product.product"].create({"name": "X4U Test Import Engine", "is_storable": True, "categ_id": engines.id})
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
                            "name": part.name,
                            "product_id": part.id,
                            "product_uom_qty": 2,
                            "product_uom": part.uom_id.id,
                            "price_unit": 1000.0,
                            "location_id": suppliers.id,
                            "location_dest_id": warehouse.lot_stock_id.id,
                        }
                    )
                ],
            }
        )
        receipt.action_confirm()
        receipt.move_ids.quantity = 2
        self._name_serials(receipt)
        receipt.move_ids.picked = True
        receipt.button_validate()
        self.assertEqual(part.value_svl, 2000.0)

        forwarder = self.env["res.partner"].create({"name": "X4U Test Forwarder"})
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": forwarder.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    Command.create({"product_id": freight.id, "quantity": 1, "price_unit": 300.0, "tax_ids": [Command.clear()]})
                ],
            }
        )
        bill.action_post()
        freight_line = bill.invoice_line_ids
        self.assertEqual(freight_line.account_id, clearing, "the bill debits the clearing account")
        action = bill.button_create_landed_costs()
        landed = self.env["stock.landed.cost"].browse(action["res_id"])
        landed.picking_ids = receipt
        landed.compute_landed_cost()
        landed.button_validate()
        self.assertEqual(landed.state, "done")
        part.invalidate_recordset()
        self.assertEqual(sum(part.stock_valuation_layer_ids.mapped("value")), 2300.0, "1,000 x 2 + 300 freight")
        lines = self.env["account.move.line"].search([("account_id", "=", clearing.id), ("parent_state", "=", "posted")])
        self.assertAlmostEqual(sum(lines.filtered(lambda l: l.move_id in (bill | landed.account_move_id)).mapped("balance")), 0.0)
        inventory = engines.property_stock_valuation_account_id
        self.assertEqual(sum(landed.account_move_id.line_ids.filtered(lambda l: l.account_id == inventory).mapped("balance")), 300.0)

    def test_fixed_asset_from_vendor_bill(self):
        """§11: a computer bought on 106003 becomes an asset with its profile; 3 years straight-line;
        each depreciation posts Dr 400065 / Cr 106008."""
        from odoo.addons.x4u_account import hooks

        Account = self.env["account.account"].with_company(self.company)

        def ensure(code, name, account_type):
            return hooks._account(self.env, self.company, code) or Account.create(
                {"code": code, "name": name, "account_type": account_type}
            )

        computer = ensure("106003", "Computer Hardware & Software", "asset_fixed")
        accumulated = ensure("106008", "Acc. Deprn.Computer Hardware & Software", "asset_fixed")
        expense = ensure("400065", "Depreciation Of Computer Hard & Soft", "expense_depreciation")
        hooks._asset_profiles(self.env, self.company)
        profile = computer.with_company(self.company).asset_profile_id
        self.assertEqual(profile.name, "Computer Hardware & Software")
        self.assertEqual((profile.method_number, profile.method_period, profile.method), (3, "month", "linear"))
        self.assertTrue(self.env.ref("account_asset_management.ir_cron_assets_generator").active)

        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor.id,
                "invoice_date": "2026-01-01",
                "date": "2026-01-01",
                "invoice_line_ids": [
                    Command.create(
                        {"name": "X4U Test Laptop", "account_id": computer.id, "quantity": 1, "price_unit": 3600.0,
                         "tax_ids": [Command.clear()]}
                    )
                ],
            }
        )
        self.assertEqual(bill.invoice_line_ids.asset_profile_id, profile)
        bill.action_post()
        asset = self.env["account.asset"].search([("profile_id", "=", profile.id), ("purchase_value", "=", 3600.0)])
        self.assertEqual(len(asset), 1, "the bill created the asset")
        asset.validate()
        asset.compute_depreciation_board()
        depreciation = asset.depreciation_line_ids.filtered(lambda line: line.type == "depreciate")
        self.assertAlmostEqual(sum(depreciation.mapped("amount")), 3600.0, places=2)
        first = depreciation.sorted("line_date")[0]
        first.create_move()
        move = first.move_id
        self.assertEqual(move.line_ids.filtered(lambda line: line.debit).account_id, expense)
        self.assertEqual(move.line_ids.filtered(lambda line: line.credit).account_id, accumulated)
        self.assertAlmostEqual(first.amount, 100.0, places=2)

    def test_fixed_assets_group_types(self):
        from odoo.addons.x4u_account import hooks

        Account = self.env["account.account"].with_company(self.company)
        account = hooks._account(self.env, self.company, "106002") or Account.create(
            {"code": "106002", "name": "Furniture and Equipment", "account_type": "asset_current"}
        )
        if not self.env["account.move.line"].search_count([("account_id", "=", account.id)]):
            account.account_type = "asset_current"
            hooks._fix_accounts(self.env, self.company)
            self.assertEqual(account.account_type, "asset_fixed")

    def test_other_methods_unchanged(self):
        manual = self.bank.outbound_payment_method_line_ids.filtered(lambda line: line.code == "manual")[:1]
        payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.vendor.id,
                "amount": 300.0,
                "journal_id": self.bank.id,
                "payment_method_line_id": manual.id,
            }
        )
        payment.action_post()
        self.assertFalse(payment.x4u_pdc_state)
        self.assertNotEqual(payment.outstanding_account_id, self.pdc_account)
