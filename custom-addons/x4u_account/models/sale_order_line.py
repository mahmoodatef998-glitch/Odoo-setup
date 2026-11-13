from odoo import Command, _, models
from odoo.tools import float_compare, float_is_zero


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _x4u_settle_cogs(self):
        """Spec §9 S6: when everything delivered on a line is invoiced (and the other way round), its
        Goods Delivered Not Invoiced must be zero; what is left goes to Cost of Sales.

        Odoo prices the cost of sales when the invoice is posted. 4U issues the tax invoice before the
        generator is made, when its cost is still 0, so Odoo posts no cost of sales, and the delivery
        only moves the value from inventory to Goods Delivered Not Invoiced. This entry moves it to
        Cost of Sales at the real value (also any difference between an estimate and the real cost),
        with the line's analytic, so the Job Order's margin sees it."""
        AccountMoveLine = self.env["account.move.line"].sudo()
        for line in self.sudo():
            company = line.company_id
            product = line.product_id.with_company(company)
            if line.display_type or not company.anglo_saxon_accounting:
                continue
            if not (product.is_storable and product.valuation == "real_time"):
                continue
            rounding = line.product_uom.rounding
            if float_is_zero(line.qty_delivered, precision_rounding=rounding):
                continue
            if float_compare(line.qty_delivered, line.qty_invoiced, precision_rounding=rounding) != 0:
                continue
            accounts = product.product_tmpl_id.get_product_accounts(fiscal_pos=line.order_id.fiscal_position_id)
            output, expense = accounts["stock_output"], accounts["expense"]
            if not output or not expense or output == expense:
                continue
            stock_lines = line.move_ids.filtered(lambda move: move.state == "done").stock_valuation_layer_ids.account_move_id.line_ids
            invoice_lines = AccountMoveLine.search([("cogs_origin_id", "in", line.invoice_lines.ids)])
            settled = AccountMoveLine.search([("x4u_cogs_sale_line_id", "=", line.id)])
            gdni = (stock_lines | invoice_lines | settled).filtered(
                lambda aml: aml.account_id == output and aml.product_id == product and aml.parent_state == "posted"
            )
            balance = company.currency_id.round(sum(gdni.mapped("balance")))
            if company.currency_id.is_zero(balance):
                continue
            journal = product.categ_id.property_stock_journal
            label = _("Cost of sales %(order)s - %(product)s", order=line.order_id.name, product=product.display_name)
            common = {
                "name": label,
                "partner_id": line.order_id.partner_id.commercial_partner_id.id,
                "product_id": product.id,
                "x4u_cogs_sale_line_id": line.id,
            }
            move = self.env["account.move"].sudo().create(
                {
                    "move_type": "entry",
                    "journal_id": journal.id,
                    "ref": label,
                    "line_ids": [
                        Command.create(
                            dict(common, account_id=expense.id, balance=balance,
                                 analytic_distribution=line.analytic_distribution or False)
                        ),
                        Command.create(dict(common, account_id=output.id, balance=-balance)),
                    ],
                }
            )
            move.action_post()
            if output.reconcile:
                (gdni | move.line_ids.filtered(lambda aml: aml.account_id == output)).filtered(
                    lambda aml: not aml.reconciled
                ).reconcile()
