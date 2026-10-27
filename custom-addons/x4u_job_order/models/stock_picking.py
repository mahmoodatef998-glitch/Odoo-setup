from odoo import _, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        res = super()._action_done()
        self._x4u_log_job_orders()
        return res

    def _x4u_log_job_orders(self):
        """Receipts, Pick Components and customer deliveries of Job Orders."""
        Production = self.env["mrp.production"].sudo()
        for picking in self.filtered(lambda p: p.state == "done"):
            moves = picking.move_ids.filtered(lambda m: m.state == "done")
            warehouse = picking.picking_type_id.warehouse_id
            if picking.picking_type_code == "incoming":
                touched = Production.browse()
                for move in moves:
                    productions = Production._x4u_from_moves(move.move_dest_ids)
                    productions._x4u_log("part_received", document=picking, detail=move.product_id.display_name)
                    touched |= productions
                touched._x4u_check_parts_ready()
            elif warehouse and picking.picking_type_id == warehouse.pbm_type_id:
                # Material Delivered once every part is delivered; a part delivered alone waits.
                for production in Production._x4u_from_moves(moves.move_dest_ids):
                    if production.x4u_job_state not in ("waiting_parts", "parts_ready"):
                        continue
                    if all(move.state == "done" for move in production._x4u_component_moves()):
                        production._x4u_set_state("material_delivered")
                        production._x4u_log("material_delivered", document=picking)
                        production._x4u_notify("operation", _("Finish Job Order %s", production.name))
            lots = picking.move_line_ids.filtered(
                lambda ml: ml.lot_id and ml.location_dest_id.usage == "customer" and ml.location_id.usage != "customer"
            ).lot_id
            if lots:
                productions = Production.search([("lot_producing_id", "in", lots.ids), ("x4u_is_job_order", "=", True)])
                productions._x4u_set_state("delivered")
                productions._x4u_log("delivered", document=picking)
