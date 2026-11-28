from odoo import _, models


class StockValueXlsx(models.AbstractModel):
    """Spec §23: Stock Value in Excel - the categories with their totals, the products, the serials
    on a sheet of their own, and the stock accounts against the books."""

    _name = "report.x4u_account.stock_value_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Stock Value (Excel)"

    def generate_xlsx_report(self, workbook, data, wizards):
        bold = workbook.add_format({"bold": True})
        title = workbook.add_format({"bold": True, "font_size": 14})
        head = workbook.add_format({"bold": True, "bg_color": "#FFDE59", "border": 1})
        money = workbook.add_format({"num_format": "#,##0.00"})
        money_bold = workbook.add_format({"num_format": "#,##0.00", "bold": True, "top": 1})
        qty = workbook.add_format({"num_format": "#,##0.##"})
        qty_bold = workbook.add_format({"num_format": "#,##0.##", "bold": True, "top": 1})
        for wizard in wizards:
            sheet = workbook.add_worksheet(_("Stock Value"))
            sheet.set_column(0, 0, 45)
            sheet.set_column(1, 4, 16)
            sheet.write(0, 0, _("Stock Value on %s - %s", wizard.date, wizard.company_id.name), title)
            row = 2
            for col, label in enumerate((_("Product"), _("Quantity"), _("Average Unit Cost"), _("Total Value"), _("Serials"))):
                sheet.write(row, col, label, head)
            row += 1
            for categ in wizard.line_ids.categ_id.sorted("complete_name"):
                lines = wizard.line_ids.filtered(lambda line, c=categ: line.categ_id == c)
                sheet.write(row, 0, categ.complete_name, bold)
                row += 1
                for line in lines.sorted(lambda line: line.product_id.display_name):
                    sheet.write(row, 0, "    " + line.product_id.display_name)
                    sheet.write_number(row, 1, line.quantity, qty)
                    sheet.write_number(row, 2, line.unit_cost, money)
                    sheet.write_number(row, 3, line.value, money)
                    sheet.write_number(row, 4, line.serial_count)
                    row += 1
                sheet.write(row, 0, _("Total %s", categ.name), bold)
                sheet.write_number(row, 1, sum(lines.mapped("quantity")), qty_bold)
                sheet.write_number(row, 3, sum(lines.mapped("value")), money_bold)
                sheet.write_number(row, 4, sum(lines.mapped("serial_count")), qty_bold)
                row += 2
            sheet.write(row, 0, _("Stock Value"), bold)
            sheet.write_number(row, 3, wizard.total_value, money_bold)
            sheet.write(row + 1, 0, _("Book Balance (stock accounts)"), bold)
            sheet.write_number(row + 1, 3, wizard.book_balance, money_bold)
            sheet.write(row + 2, 0, _("Difference"), bold)
            sheet.write_number(row + 2, 3, wizard.difference, money_bold)
            row += 4
            for col, label in enumerate((_("Account"), _("Stock Value"), _("Book Balance"), _("Difference"))):
                sheet.write(row, col, label, head)
            row += 1
            for account in wizard.account_ids.sudo():
                sheet.write(row, 0, account.account_id.display_name or _("(no stock account)"))
                sheet.write_number(row, 1, account.stock_value, money)
                sheet.write_number(row, 2, account.book_balance, money)
                sheet.write_number(row, 3, account.difference, money)
                row += 1

            serials = workbook.add_worksheet(_("Serials"))
            serials.set_column(0, 1, 40)
            serials.set_column(2, 3, 16)
            for col, label in enumerate((_("Product"), _("Serial"), _("Quantity"), _("Cost"))):
                serials.write(0, col, label, head)
            row = 1
            for line in wizard.line_ids.sorted(lambda line: (line.categ_id.complete_name or "", line.product_id.display_name)):
                for lot in line.lot_ids:
                    serials.write(row, 0, line.product_id.display_name)
                    serials.write(row, 1, lot.lot_id.name or "")
                    serials.write_number(row, 2, lot.quantity, qty)
                    serials.write_number(row, 3, lot.value, money)
                    row += 1
