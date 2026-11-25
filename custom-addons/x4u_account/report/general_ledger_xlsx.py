from odoo import _, models

# Spec §22 G2: a balance reads 1,250.00 Dr / 1,250.00 Cr and stays a number Excel adds up.
DR_CR = '#,##0.00 "Dr";#,##0.00 "Cr";0.00'


class GeneralLedgerXlsx(models.AbstractModel):
    _inherit = "report.a_f_r.report_general_ledger_xlsx"

    def _get_report_columns(self, report):
        columns = list(super()._get_report_columns(report).values())
        position = next((i for i, col in enumerate(columns) if col.get("field") == "partner_name"), len(columns) - 1)
        columns.insert(position + 1, {"header": _("Counterpart"), "field": "x4u_counterpart", "width": 30})
        return dict(enumerate(columns))

    def _define_formats(self, workbook, report_data, data=None):
        res = super()._define_formats(workbook, report_data, data=data)
        formats = report_data["formats"]
        formats["x4u_dr_cr"] = workbook.add_format({"num_format": DR_CR})
        formats["x4u_dr_cr_header"] = workbook.add_format(
            {"num_format": DR_CR, "bold": True, "border": True, "bg_color": "#FFFFCC"}
        )
        return res

    def _x4u_rewrite_balance(self, report_data, value, header=False):
        """Write the balance cell of the line just written again, with Dr / Cr."""
        for col_pos, column in report_data["columns"].items():
            if column.get("field") == "balance":
                report_data["sheet"].write_number(
                    report_data["row_pos"] - 1, col_pos, self._round_value_by_currency(value or 0.0),
                    report_data["formats"]["x4u_dr_cr_header" if header else "x4u_dr_cr"],
                )

    def write_line_from_dict(self, line_dict, report_data):
        res = super().write_line_from_dict(line_dict, report_data)
        if "balance" in line_dict and not line_dict.get("account_group_id"):
            self._x4u_rewrite_balance(report_data, line_dict["balance"])
        return res

    def write_initial_balance_from_dict(self, my_object, report_data):
        res = super().write_initial_balance_from_dict(my_object, report_data)
        self._x4u_rewrite_balance(report_data, my_object.get("initial_balance"))
        return res

    def write_ending_balance_from_dict(self, my_object, report_data):
        res = super().write_ending_balance_from_dict(my_object, report_data)
        self._x4u_rewrite_balance(report_data, my_object.get("final_balance"), header=True)
        return res
