from odoo import fields, models

from .x4u_generator import DELIVERY_FIELDS


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        # No quality gate before delivery since 2026-10-27 (x4u_job_order spec v0.4 V7,
        # spec Q3 cancelled); the card still shows the QC status of any inspection.
        res = super()._action_done()
        self._x4u_update_generator_cards()
        return res

    def _x4u_update_generator_cards(self):
        """Fill the card on delivery, clear it on return (spec R4/R5)."""
        for line in self.move_line_ids.filtered(
            lambda ml: ml.state == "done" and ml.lot_id
        ):
            cards = line.lot_id.sudo().x4u_generator_ids
            if not cards:
                continue
            to_customer = line.location_dest_id.usage == "customer"
            from_customer = line.location_id.usage == "customer"
            if to_customer and not from_customer:
                picking = line.picking_id
                cards.write(
                    {
                        "customer_id": picking.partner_id.commercial_partner_id.id,
                        "site_address_id": picking.partner_id.id,
                        "sale_order_id": line.move_id.sale_line_id.order_id.id,
                        "delivery_picking_id": picking.id,
                        "delivery_date": fields.Date.context_today(
                            self, picking.date_done
                        ),
                        "commissioning_date": False,
                    }
                )
            elif from_customer and not to_customer:
                cards.write(dict.fromkeys(DELIVERY_FIELDS, False))
