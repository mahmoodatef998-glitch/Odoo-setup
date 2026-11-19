from odoo import api, models


class StockRule(models.Model):
    _inherit = "stock.rule"

    @api.model
    def _run_manufacture(self, procurements):
        """One Job Order per generator (spec v0.4 V8): a sale of 3 opens 3 Job Orders,
        each with its own serial, parts and flag. Odoo splits by "batch_size"."""
        for procurement, _rule in procurements:
            if procurement.product_id.x4u_is_generator:
                procurement.values["batch_size"] = 1
        return super()._run_manufacture(procurements)

    def _prepare_mo_vals(self, product_id, product_qty, product_uom, location_dest_id, name, origin, company_id, values, bom):
        """Spec v0.12 J1: every generator of a sales order goes in the order's one Job Order."""
        vals = super()._prepare_mo_vals(product_id, product_qty, product_uom, location_dest_id, name, origin, company_id, values, bom)
        if product_id.x4u_is_generator and not vals.get("x4u_job_id"):
            order = self._x4u_sale_order(values)
            if order:
                vals["x4u_job_id"] = self.env["x4u.job.order"]._x4u_for_order(order, self.picking_type_id).id
        return vals

    def _x4u_sale_order(self, values):
        line = self.env["sale.order.line"].sudo().browse(values.get("sale_line_id") or [])
        order = line.order_id
        if not order and values.get("move_dest_ids"):
            order = values["move_dest_ids"].sudo().sale_line_id.order_id[:1]
        if not order and values.get("group_id"):
            order = values["group_id"].sudo().sale_id
        return order
