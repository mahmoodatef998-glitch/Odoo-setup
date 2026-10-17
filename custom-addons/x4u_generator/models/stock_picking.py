from odoo import _, fields, models
from odoo.exceptions import UserError

from .x4u_generator import DELIVERY_FIELDS


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        self._x4u_check_generator_quality()
        res = super()._action_done()
        self._x4u_update_generator_cards()
        return res

    def _x4u_check_generator_quality(self):
        """Block delivering a generator whose QC didn't pass (spec Q3).

        Inventory Administrators may go ahead; it is logged on the card.
        """
        lines = self.move_line_ids.filtered(
            lambda ml: ml.lot_id
            and ml.picked
            and ml.quantity > 0
            and ml.location_dest_id.usage == "customer"
            and ml.location_id.usage != "customer"
        )
        cards = lines.lot_id.sudo().x4u_generator_ids.filtered(
            lambda card: card.qc_state != "passed"
        )
        if not cards:
            return
        qc_labels = dict(cards._fields["qc_state"]._description_selection(self.env))
        if not self.env.user.has_group("stock.group_stock_manager"):
            raise UserError(
                _(
                    "These generators can't be delivered to a customer before they "
                    "pass quality inspection:\n%(generators)s\n\n"
                    "Ask an Inventory Administrator if the delivery must go ahead.",
                    generators="\n".join(
                        f"- {card.name} ({qc_labels[card.qc_state]})" for card in cards
                    ),
                )
            )
        for card in cards:
            card.message_post(
                body=_(
                    "Delivered to a customer without a passed quality inspection "
                    "(QC status: %(state)s), approved by %(user)s.",
                    state=qc_labels[card.qc_state],
                    user=self.env.user.name,
                )
            )

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
