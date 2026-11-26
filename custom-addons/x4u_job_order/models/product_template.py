from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError

from .stock_move import part_role

# Spec v0.8 N1 / v0.9 C1 / v0.10 B1: parts that go in and out by their serial, each valued at its own price.
# x4u_account spec §20 P3 (UAT 2026-11-24): a product of the Generators category too (a ready
# generator bought complete was made in "All" without its serial).
SERIAL_CATEGORIES = (
    "x4u_setup_base.categ_engines", "x4u_setup_base.categ_ckd", "x4u_setup_base.categ_bodies",
    "x4u_setup_base.categ_generators",
)


class ProductProduct(models.Model):
    _inherit = "product.product"

    # The user, 2026-11-26: the full CKD (engine + alternator, one serial) this generator is built from.
    x4u_ckd_product_id = fields.Many2one(
        "product.product", string="CKD", copy=False, readonly=True,
        help="The CKD of this model's engine and alternator, made when the model is ticked Built from CKD.",
    )

    @api.model
    def _x4u_ckd_for(self, engine, alternator):
        """The full CKD card of this engine + alternator (CKD-<engine>-<alternator>, category CKD, by
        serial = the engine's, the engine's vendor and routes), made the first time it is needed."""

        def short(product, prefix):
            code = product.default_code or product.name
            return code[len(prefix):] if code.startswith(prefix) else code

        Product = self.sudo()
        code = "CKD-%s-%s" % (short(engine, "ENG-"), short(alternator, "ALT-"))
        ckd = Product.with_context(active_test=False).search([("default_code", "=", code)], limit=1)
        if not ckd:
            seller = engine.seller_ids[:1]
            ckd = Product.create(
                {
                    "name": "CKD %s + %s" % (engine.name, alternator.name),
                    "default_code": code,
                    "categ_id": self.env.ref("x4u_setup_base.categ_ckd").id,
                    "is_storable": True,
                    "tracking": "serial",
                    "purchase_request": engine.purchase_request,
                    "route_ids": [Command.set(engine.route_ids.ids)],
                    "seller_ids": [Command.create({"partner_id": seller.partner_id.id})] if seller else [],
                }
            )
        return ckd

    def _x4u_order_needs(self, exclude_lines=None):
        """Spec v0.15 B1: (what the open Job Orders still need, free in WH/Stock, coming in), in the
        product's unit. The need: Pick Components of open Job Orders not delivered yet, and the ready
        generators still to buy."""
        self.ensure_one()
        product = self.sudo()
        Move = self.env["stock.move"].sudo()
        warehouses = self.env["stock.warehouse"].sudo().search([("company_id", "in", self.env.companies.ids)])
        picks = Move.search(
            [
                ("product_id", "=", product.id),
                ("picking_type_id", "in", warehouses.pbm_type_id.ids),
                ("state", "not in", ("done", "cancel")),
                ("move_dest_ids.raw_material_production_id.x4u_is_job_order", "=", True),
            ]
        )
        need = sum(picks.mapped("product_qty"))
        if product.x4u_is_generator:
            need += self.env["x4u.ready.order"].sudo().search_count([("product_id", "=", product.id), ("state", "=", "waiting")])
        free = sum(product.with_context(location=warehouse.lot_stock_id.id).free_qty for warehouse in warehouses)
        lines = self.env["purchase.order.line"].sudo().search(
            [
                ("product_id", "=", product.id),
                ("state", "in", ("draft", "sent", "to approve", "purchase")),
                ("id", "not in", (exclude_lines or self.env["purchase.order.line"]).ids),
            ]
        )
        incoming = sum(
            max(line.product_uom._compute_quantity(line.product_qty - line.qty_received, product.uom_id), 0.0)
            for line in lines
        )
        # Receipts without a purchase order (bought another way) count too.
        receipts = Move.search(
            [
                ("product_id", "=", product.id),
                ("picking_code", "=", "incoming"),
                ("purchase_line_id", "=", False),
                ("state", "not in", ("draft", "done", "cancel")),
            ]
        )
        incoming += sum(receipts.mapped("product_qty"))
        return need, free, incoming


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # The user, 2026-11-26: a model built from a full CKD - its Job Orders take the CKD instead of the
    # engine and the alternator by themselves; the Operation Manager can still switch back.
    x4u_built_from_ckd = fields.Boolean(
        string="Built from CKD", copy=False,
        help="Its Job Orders use the CKD (engine + alternator on one serial) instead of a separate engine and "
        "alternator. Ticking it makes the CKD card of each alternator variant.",
    )
    x4u_ckd_product_ids = fields.Many2many(
        "product.product", string="CKD Parts", compute="_compute_x4u_ckd_product_ids",
    )

    @api.depends("product_variant_ids.x4u_ckd_product_id")
    def _compute_x4u_ckd_product_ids(self):
        for template in self:
            template.x4u_ckd_product_ids = template.product_variant_ids.x4u_ckd_product_id

    def write(self, vals):
        res = super().write(vals)
        if vals.get("x4u_built_from_ckd"):
            self._x4u_make_ckd_products()
        return res

    def _x4u_make_ckd_products(self):
        """The CKD card of each variant: its engine + its alternator from the bill of materials, as
        one product of the CKD category (by serial = the engine's), with the engine's vendor and
        routes. One card per engine + alternator pair, shared by the models that have it."""
        for variant in self.sudo().product_variant_ids:
            bom = self.env["mrp.bom"].sudo()._bom_find(variant, company_id=self.env.company.id).get(variant)
            if not bom:
                continue
            parts = bom.bom_line_ids.filtered(lambda line, v=variant: not line._skip_bom_line(v)).product_id
            engine = parts.filtered(lambda p: part_role(self.env, p) == "engine")[:1]
            alternator = parts.filtered(lambda p: part_role(self.env, p) == "alternator")[:1]
            if not engine or not alternator:
                continue
            variant.x4u_ckd_product_id = self.env["product.product"]._x4u_ckd_for(engine, alternator)

    @api.model
    def _x4u_serial_categories(self):
        return [categ for categ in (self.env.ref(xmlid, raise_if_not_found=False) for xmlid in SERIAL_CATEGORIES) if categ]

    @api.model
    def _x4u_serial_category(self, category):
        """An engine, CKD or genset body category (or one under it)."""
        path = category.parent_path or ""
        return bool(category) and any(path.startswith(categ.parent_path) for categ in self._x4u_serial_categories())

    def _x4u_by_serial(self):
        """An engine, a CKD or a genset body: tracked and valued by its serial."""
        self.ensure_one()
        return self._x4u_serial_category(self.categ_id)

    @api.depends("tracking", "x4u_is_generator", "categ_id")
    def _compute_lot_valuated(self):
        """Each generator keeps its own value (parts + overhead, spec v0.4 V5), and each engine, CKD
        and body what was paid for it (spec v0.8 N1, v0.9 C1, v0.10 B1)."""
        super()._compute_lot_valuated()
        for template in self:
            if template.tracking == "serial" and (template.x4u_is_generator or template._x4u_by_serial()):
                template.lot_valuated = True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            categ = self.env["product.category"].browse(vals.get("categ_id"))
            # Odoo fills the default "none" in before this point (a product.product create).
            if vals.get("is_storable") and vals.get("tracking", "none") == "none" and self._x4u_serial_category(categ):
                vals["tracking"] = "serial"
        return super().create(vals_list)

    @api.onchange("categ_id", "is_storable")
    def _onchange_x4u_engine_serial(self):
        if self.is_storable and self._x4u_by_serial():
            self.tracking = "serial"

    @api.constrains("categ_id", "tracking", "is_storable")
    def _check_x4u_engine_serial(self):
        for template in self:
            if template.is_storable and template.tracking != "serial" and template._x4u_by_serial():
                raise ValidationError(
                    _(
                        "%s is an engine, a CKD, a genset body or a generator: each one is tracked by its serial number "
                        "(Tracking: By Unique Serial Number).",
                        template.display_name,
                    )
                )
