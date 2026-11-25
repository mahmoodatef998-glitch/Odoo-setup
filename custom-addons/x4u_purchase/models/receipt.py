from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = "res.company"

    # UAT Phase 2.2 (the user, 2026-11-25: "Required"): a receipt from a vendor is validated with the
    # vendor's signed Delivery Note attached. On for 4U by the migration; off on a new database.
    x4u_receipt_dn_required = fields.Boolean(string="Delivery Note Required on Receipts")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    x4u_receipt_dn_required = fields.Boolean(related="company_id.x4u_receipt_dn_required", readonly=False)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    x4u_delivery_note_ids = fields.Many2many(
        "ir.attachment", "x4u_picking_delivery_note_rel", "picking_id", "attachment_id",
        string="Delivery Note", copy=False,
        help="The vendor's delivery note, signed when the goods came in (photo or scan). It goes to the vendor bill.",
    )
    x4u_vendor_ref = fields.Char(
        string="Vendor Invoice No.", copy=False,
        help="The vendor's invoice (or delivery note) number on the papers that came with the goods. "
        "It goes to the Accountant's notification and to the bill's reference.",
    )
    x4u_is_vendor_receipt = fields.Boolean(compute="_compute_x4u_is_vendor_receipt")
    x4u_bill_ids = fields.One2many("account.move", "x4u_receipt_id", string="Vendor Bills")
    x4u_billed = fields.Boolean(string="Billed", compute="_compute_x4u_billed", search="_search_x4u_billed")

    @api.depends("picking_type_code", "location_id.usage")
    def _compute_x4u_is_vendor_receipt(self):
        for picking in self:
            picking.x4u_is_vendor_receipt = picking.picking_type_code == "incoming" and picking.location_id.usage == "supplier"

    def _compute_x4u_billed(self):
        for picking in self:
            picking.x4u_billed = bool(picking.x4u_bill_ids.filtered(lambda bill: bill.state != "cancel"))

    def _search_x4u_billed(self, operator, value):
        bills = self.env["account.move"].sudo().search([("x4u_receipt_id", "!=", False), ("state", "!=", "cancel")])
        billed = bills.x4u_receipt_id.ids
        positive = (operator == "=") == bool(value)
        return [("id", "in" if positive else "not in", billed)]

    def button_validate(self):
        """UAT Phase 2.2: no receipt from a vendor without its Delivery Note."""
        missing = self.filtered(
            lambda p: p.x4u_is_vendor_receipt and p.company_id.x4u_receipt_dn_required and not p.x4u_delivery_note_ids
        )
        if missing:
            raise UserError(
                _("Attach the vendor's Delivery Note (photo or scan) to %s before validating it.", ", ".join(missing.mapped("name")))
            )
        return super().button_validate()

    def _action_done(self):
        res = super()._action_done()
        self.filtered(lambda p: p.state == "done" and p.x4u_is_vendor_receipt)._x4u_ask_vendor_bill()
        return res

    def _x4u_received_lines(self):
        """[(product, quantity with its unit, serials)] of what came in on this receipt."""
        self.ensure_one()
        rows = []
        for move in self.move_ids.filtered(lambda m: m.state == "done" and m.quantity):
            serials = move.move_line_ids.lot_id.mapped("name") or [n for n in move.move_line_ids.mapped("lot_name") if n]
            if not serials and "x4u_alternator_serials" in move._fields and move.x4u_alternator_serials:
                serials = [s.strip() for s in move.x4u_alternator_serials.replace(";", ",").split(",") if s.strip()]
            rows.append((move.product_id.display_name, "%g %s" % (move.quantity, move.product_uom.name), serials))
        return rows

    def _x4u_ask_vendor_bill(self):
        """UAT Phase 2.2 (the user, 2026-11-25): the Accountant is notified of what came in - the
        receipt, the vendor's invoice number, each item with its serials, the Delivery Note - and has a
        task to record the bill."""
        user_id = int(self.env["ir.config_parameter"].sudo().get_param("x4u_sale.accountant_user_id") or 0)
        user = self.env["res.users"].sudo().browse(user_id).exists()
        if not user:
            return
        for picking in self.sudo():
            order = picking.purchase_id
            if not order:
                continue
            items = Markup("").join(
                Markup("<li>%s: <b>%s</b>%s</li>") % (
                    product, quantity, Markup(" · SN %s") % ", ".join(serials) if serials else "",
                )
                for product, quantity, serials in picking._x4u_received_lines()
            )
            body = Markup(
                "<p><b>Goods received: %(receipt)s</b> from %(vendor)s (PO %(order)s)<br/>"
                "Vendor invoice no.: <b>%(ref)s</b></p><ul>%(items)s</ul>"
                "<p>Record the vendor bill: Vendor Bill &gt; Receipt %(receipt)s.</p>"
            ) % {
                "receipt": picking.name, "vendor": picking.partner_id.commercial_partner_id.display_name,
                "order": order.name, "ref": picking.x4u_vendor_ref or "-", "items": items,
            }
            copies = [a.copy({"res_model": "purchase.order", "res_id": order.id}).id for a in picking.x4u_delivery_note_ids]
            order.message_post(
                body=body, partner_ids=user.partner_id.ids, subtype_xmlid="mail.mt_comment",
                message_type="comment", attachment_ids=copies,
            )
            order.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                summary=_("Vendor bill: %s", picking.name),
                note=_("%(receipt)s came in from %(vendor)s (Delivery Note attached to the receipt). Record the vendor bill: "
                       "Vendor Bill > Receipt %(receipt)s.", receipt=picking.name, vendor=picking.partner_id.display_name),
            )
