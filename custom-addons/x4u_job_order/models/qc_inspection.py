from odoo import models


class QcInspection(models.Model):
    _inherit = "qc.inspection"

    def write(self, vals):
        res = super().write(vals)
        if vals.get("state") in ("success", "failed"):
            Production = self.env["mrp.production"].sudo()
            for inspection in self.filtered("lot_id"):
                productions = Production.search([("lot_producing_id", "=", inspection.lot_id.id)])
                event = "qc_passed" if inspection.state == "success" else "qc_failed"
                productions._x4u_log(event, document=inspection)
        return res
