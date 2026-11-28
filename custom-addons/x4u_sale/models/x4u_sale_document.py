from odoo import api, fields, models


class X4uSaleDocumentType(models.Model):
    """Spec v0.9 C3: a document some customers send with each order (trade licence, TRN
    certificate...). Ticked once on the customer, it is on the checklist of every order of it."""

    _name = "x4u.sale.document.type"
    _description = "Order Document Type"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [("name_unique", "unique(name)", "This document type exists already.")]


class X4uSaleOrderDocument(models.Model):
    """The file of one required document on one order (v0.9 C3)."""

    _name = "x4u.sale.order.document"
    _description = "Order Document"
    _order = "order_id, sequence, id"

    order_id = fields.Many2one("sale.order", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True)
    type_id = fields.Many2one("x4u.sale.document.type", string="Document", required=True, ondelete="restrict")
    sequence = fields.Integer(related="type_id.sequence", store=True)
    attachment_ids = fields.Many2many(
        "ir.attachment", "x4u_sale_order_document_attachment_rel", "document_id", "attachment_id", string="File"
    )
    done = fields.Boolean(compute="_compute_done", string="Uploaded")

    _sql_constraints = [("type_unique", "unique(order_id, type_id)", "The order has this document already.")]

    @api.depends("attachment_ids")
    def _compute_done(self):
        for document in self:
            document.done = bool(document.attachment_ids)

    @api.model_create_multi
    def create(self, vals_list):
        documents = super().create(vals_list)
        documents._x4u_own_files()
        return documents

    def write(self, vals):
        res = super().write(vals)
        if "attachment_ids" in vals:
            self._x4u_own_files()
        return res

    def _x4u_own_files(self):
        """The Accountant opens what the Salesperson uploaded: the files belong to the order."""
        for document in self:
            loose = document.attachment_ids.sudo().filtered(lambda attachment: not attachment.res_id)
            if loose:
                loose.write({"res_model": "sale.order", "res_id": document.order_id.id})
