from collections import Counter

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


def free_lots(env, move):
    """The serials of the move's product that WH/Stock (or the move's source) can still give."""
    if not move or move.has_tracking != "serial":
        return env["stock.lot"]
    quants = env["stock.quant"].sudo().search(
        [
            ("product_id", "=", move.product_id.id),
            ("location_id", "child_of", move.location_id.id),
            ("lot_id", "!=", False),
            ("quantity", ">", 0),
        ]
    )
    return quants.filtered(lambda q: q.quantity > q.reserved_quantity).lot_id


def factory_lots(env, move):
    """Spec v0.11 D2: the serials of the move's product in the factory (WH/Pre-Production), whichever
    Job Order they were delivered to."""
    if not move or move.has_tracking != "serial":
        return env["stock.lot"]
    return env["stock.quant"].sudo().search(
        [("product_id", "=", move.product_id.id), ("location_id", "child_of", move.location_id.id), ("lot_id", "!=", False), ("quantity", ">", 0)]
    ).lot_id


class X4uJobOrderDeliverAll(models.TransientModel):
    """Spec v0.11 D1: the parts of several Job Orders (the generators of one order) in one screen, a
    line per generator. Each line then goes through Deliver Materials of its own Job Order (V3, N3),
    so the rules are the same: a part by serial goes only with its serial."""

    _name = "x4u.job.order.deliver.all"
    _description = "Deliver Materials of Several Job Orders"

    line_ids = fields.One2many("x4u.job.order.deliver.all.line", "wizard_id", string="Generators")

    @api.model
    def _x4u_action(self, productions):
        lines = []
        # The user, 2026-11-26 (fewer steps): a part not chosen on the Serial tab is filled with the
        # oldest serial still free, never one chosen for (or given to) another generator here.
        taken_lots = productions.x4u_engine_lot_id | productions.x4u_body_lot_id
        taken_alternators = productions.x4u_alternator_id

        def oldest_lot(move):
            return (free_lots(self.env, move) - taken_lots).sorted("id")[:1]

        def oldest_alternator(move):
            if not move:
                return self.env["x4u.alternator.serial"]
            return self.env["x4u.alternator.serial"].search(
                [("product_id", "=", move.product_id.id), ("state", "=", "in_stock"), ("id", "not in", taken_alternators.ids)],
                order="id", limit=1,
            )

        for production in productions.sorted("name"):
            moves = production._x4u_pick_components().move_ids.filtered(lambda m: m.state not in ("done", "cancel"))
            if not moves:
                continue

            def first(roles, moves=moves):
                return moves.filtered(lambda m: m.x4u_role in roles)[:1]

            engine, alternator, body = first(("engine", "ckd")), first(("alternator",)), first(("body",))
            # Spec v0.12 J4: filled with the serials chosen on the Serial tab, if still free.
            chosen_engine = production.x4u_engine_lot_id if production.x4u_engine_lot_id in free_lots(self.env, engine) else False
            chosen_body = production.x4u_body_lot_id if production.x4u_body_lot_id in free_lots(self.env, body) else False
            chosen_alternator = production.x4u_alternator_id.filtered(
                lambda s, a=alternator: s.state == "in_stock" and s.product_id == a.product_id
            )
            chosen_engine = chosen_engine or oldest_lot(engine)
            chosen_body = chosen_body or oldest_lot(body)
            chosen_alternator = chosen_alternator or oldest_alternator(alternator)
            taken_lots |= (chosen_engine or self.env["stock.lot"]) | (chosen_body or self.env["stock.lot"])
            taken_alternators |= chosen_alternator
            lines.append(
                Command.create(
                    {
                        "production_id": production.id,
                        "engine_move_id": engine.id,
                        "engine_lot_id": chosen_engine and chosen_engine.id,
                        "alternator_move_id": alternator.id,
                        "alternator_serial_id": chosen_alternator[:1].id,
                        "body_move_id": body.id,
                        "body_lot_id": chosen_body and chosen_body.id,
                    }
                )
            )
        if not lines:
            raise UserError(_("These Job Orders have no material left to deliver."))
        wizard = self.create({"line_ids": lines})
        return {
            "type": "ir.actions.act_window",
            "name": _("Deliver Materials"),
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_confirm(self):
        self.ensure_one()
        problems = []
        lots = Counter(lot for line in self.line_ids for lot in (line.engine_lot_id, line.body_lot_id) if lot)
        alternators = Counter(line.alternator_serial_id for line in self.line_ids if line.alternator_serial_id)
        twice = [record.name for record, count in list(lots.items()) + list(alternators.items()) if count > 1]
        if twice:
            problems.append(_("- Chosen for two generators: %s", ", ".join(twice)))
        for line in self.line_ids:
            for lot, allowed in ((line.engine_lot_id, line.available_engine_lot_ids), (line.body_lot_id, line.available_body_lot_ids)):
                if lot and lot not in allowed:
                    problems.append(_("- %(job)s: %(lot)s is not in stock", job=line.production_id.name, lot=lot.name))
        if problems:
            raise UserError(_("Check these serials:\n%s", "\n".join(problems)))
        # A generator goes when a serial is picked for it, or when its engine / CKD and canopy are
        # already delivered and only the alternator or other parts are left (2026-11-20: a generator
        # whose alternator stayed behind could never be finished).
        lines = self.line_ids.filtered(
            lambda line: line.engine_lot_id or line.body_lot_id or not (line.engine_move_id or line.body_move_id)
        )
        if not lines:
            raise UserError(_("Pick the engine (or CKD) or canopy serial of at least one generator."))
        Deliver = self.env["x4u.job.order.deliver"]
        for line in lines:
            production = line.production_id
            moves = production._x4u_pick_components().move_ids.filtered(lambda m: m.state not in ("done", "cancel"))
            wizard = Deliver.create(
                {"production_id": production.id, "line_ids": [Command.create(vals) for vals in Deliver._x4u_line_values(moves)]}
            )
            chosen = {line.engine_move_id: line.engine_lot_id, line.body_move_id: line.body_lot_id}
            alternator_given = False
            for wizard_line in wizard.line_ids:
                lot = chosen.get(wizard_line.move_id)
                if lot and wizard_line.tracking == "serial":
                    wizard_line.lot_id = lot
                    chosen[wizard_line.move_id] = False
                elif wizard_line.move_id == line.alternator_move_id and line.alternator_serial_id and not alternator_given:
                    wizard_line.write({"alternator_serial_id": line.alternator_serial_id.id, "quantity": 1.0})
                    alternator_given = True
            wizard.action_confirm()
        return {"type": "ir.actions.act_window_close"}


class X4uJobOrderDeliverAllLine(models.TransientModel):
    _name = "x4u.job.order.deliver.all.line"
    _description = "Deliver Materials of Several Job Orders: Generator"
    _order = "production_id"

    wizard_id = fields.Many2one("x4u.job.order.deliver.all", required=True, ondelete="cascade")
    production_id = fields.Many2one("mrp.production", string="Job Order", required=True, readonly=True)
    product_id = fields.Many2one(related="production_id.product_id", string="Model")
    engine_move_id = fields.Many2one("stock.move", readonly=True)
    engine_product_id = fields.Many2one(related="engine_move_id.product_id", string="Engine / CKD")
    available_engine_lot_ids = fields.Many2many("stock.lot", compute="_compute_available")
    engine_lot_id = fields.Many2one("stock.lot", string="Engine / CKD Serial")
    alternator_move_id = fields.Many2one("stock.move", readonly=True)
    available_alternator_ids = fields.Many2many("x4u.alternator.serial", compute="_compute_available")
    alternator_serial_id = fields.Many2one("x4u.alternator.serial", string="Alternator Serial")
    body_move_id = fields.Many2one("stock.move", readonly=True)
    available_body_lot_ids = fields.Many2many("stock.lot", compute="_compute_available")
    body_lot_id = fields.Many2one("stock.lot", string="Canopy Serial")

    @api.depends("engine_move_id", "alternator_move_id", "body_move_id")
    def _compute_available(self):
        Serial = self.env["x4u.alternator.serial"].sudo()
        for line in self:
            line.available_engine_lot_ids = free_lots(self.env, line.engine_move_id)
            line.available_body_lot_ids = free_lots(self.env, line.body_move_id)
            line.available_alternator_ids = (
                Serial.search([("product_id", "=", line.alternator_move_id.product_id.id), ("state", "=", "in_stock")])
                if line.alternator_move_id
                else Serial
            )


class X4uJobOrderFinish(models.TransientModel):
    """Spec v0.11 D2: Finish Job Order shows the serials fitted in the generator, filled with what was
    delivered to it. If the factory fitted another unit of the same part (from another generator of
    the order), it is changed here, and that Job Order takes this one's unit instead."""

    _name = "x4u.job.order.finish"
    _description = "Finish Job Order: Serials Fitted"
    _order = "production_id"

    # Spec v0.12 J4: a line of Finish on the Job Order, one per generator.
    batch_id = fields.Many2one("x4u.job.order.finish.all", ondelete="cascade")
    production_id = fields.Many2one("mrp.production", string="Job Order", required=True, readonly=True)
    product_id = fields.Many2one(related="production_id.product_id", string="Model")
    engine_move_id = fields.Many2one("stock.move", readonly=True)
    engine_product_id = fields.Many2one(related="engine_move_id.product_id", string="Engine / CKD")
    available_engine_lot_ids = fields.Many2many("stock.lot", compute="_compute_available")
    engine_lot_id = fields.Many2one("stock.lot", string="Engine / CKD Serial")
    alternator_move_id = fields.Many2one("stock.move", readonly=True)
    alternator_product_id = fields.Many2one(related="alternator_move_id.product_id", string="Alternator")
    available_alternator_ids = fields.Many2many("x4u.alternator.serial", compute="_compute_available")
    alternator_serial_id = fields.Many2one(
        "x4u.alternator.serial", string="Alternator Serial", help="Optional (spec v0.8.1 N4): a new serial can be written here."
    )
    body_move_id = fields.Many2one("stock.move", readonly=True)
    body_product_id = fields.Many2one(related="body_move_id.product_id", string="Canopy")
    available_body_lot_ids = fields.Many2many("stock.lot", compute="_compute_available")
    body_lot_id = fields.Many2one("stock.lot", string="Canopy Serial")

    @api.model
    def _x4u_values(self, production):
        """The serials fitted in the generator, filled with what was delivered to it."""
        production._x4u_reserve_delivered_parts()
        raw = production.move_raw_ids.filtered(lambda m: m.state not in ("done", "cancel"))

        def first(roles):
            return raw.filtered(lambda m: m.x4u_role in roles)[:1]

        engine, alternator, body = first(("engine", "ckd")), first(("alternator",)), first(("body",))
        card = production.lot_producing_id.sudo().x4u_generator_id
        fitted = self.env["x4u.alternator.serial"].sudo().search([("production_id", "=", production.id)], limit=1)
        return {
            "production_id": production.id,
            "engine_move_id": engine.id,
            "engine_lot_id": (engine.move_line_ids.lot_id[:1] or card.x4u_engine_lot_id).id if engine.has_tracking == "serial" else False,
            "alternator_move_id": alternator.id,
            "alternator_serial_id": fitted.id,
            "body_move_id": body.id,
            "body_lot_id": (body.move_line_ids.lot_id[:1] or card.x4u_body_lot_id).id if body.has_tracking == "serial" else False,
        }

    @api.model
    def _x4u_action(self, production):
        wizard = self.create(self._x4u_values(production))
        return {
            "type": "ir.actions.act_window",
            "name": _("Finish Job Order · %s", production.name),
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.depends("engine_move_id", "alternator_move_id", "body_move_id")
    def _compute_available(self):
        Serial = self.env["x4u.alternator.serial"].sudo()
        for wizard in self:
            wizard.available_engine_lot_ids = factory_lots(self.env, wizard.engine_move_id)
            wizard.available_body_lot_ids = factory_lots(self.env, wizard.body_move_id)
            alternators = Serial
            if wizard.alternator_move_id:
                alternators = Serial.search([("product_id", "=", wizard.alternator_move_id.product_id.id)]).filtered(
                    lambda s: s.state == "in_stock" or s.production_id.state not in ("done", "cancel")
                )
            wizard.available_alternator_ids = alternators

    def action_confirm(self):
        self.ensure_one()
        production = self.production_id
        production._x4u_check_finish()
        missing = []
        if self.engine_move_id.has_tracking == "serial" and not self.engine_lot_id:
            missing.append(_("Engine / CKD"))
        if self.body_move_id.has_tracking == "serial" and not self.body_lot_id:
            missing.append(_("Canopy"))
        if missing:
            raise UserError(_("%(job)s: pick the serial fitted for %(parts)s.", job=production.name, parts=", ".join(missing)))
        others = self.env["mrp.production"]
        for move, lot, allowed in (
            (self.engine_move_id, self.engine_lot_id, self.available_engine_lot_ids),
            (self.body_move_id, self.body_lot_id, self.available_body_lot_ids),
        ):
            if move and lot:
                if lot not in allowed:
                    raise UserError(_("%s is not in the factory.", lot.name))
                others |= production._x4u_fit_lot(move, lot)
        if self.alternator_serial_id:
            if self.alternator_serial_id.product_id != self.alternator_move_id.product_id:
                raise UserError(_("%s is not a serial of this alternator.", self.alternator_serial_id.name))
            others |= production._x4u_fit_alternator(self.alternator_serial_id)
        for other in others - production:
            other._x4u_card_parts(other.move_raw_ids.filtered(lambda m: m.state not in ("done", "cancel")))
        return production._x4u_finish()


class X4uJobOrderFinishAll(models.TransientModel):
    """Spec v0.12 J4: Finish on the Job Order, a line per generator whose parts are delivered. Each
    line is Finish Job Order of its generator (D2): the serials fitted, swapped if the factory
    mixed them between two generators."""

    _name = "x4u.job.order.finish.all"
    _description = "Finish the Generators of a Job Order"

    line_ids = fields.One2many("x4u.job.order.finish", "batch_id", string="Generators")

    @api.model
    def _x4u_action(self, productions):
        Line = self.env["x4u.job.order.finish"]
        wizard = self.create(
            {"line_ids": [Command.create(Line._x4u_values(production)) for production in productions.sorted("name")]}
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Finish"),
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_confirm(self):
        self.ensure_one()
        lots = Counter(lot for line in self.line_ids for lot in (line.engine_lot_id, line.body_lot_id) if lot)
        alternators = Counter(line.alternator_serial_id for line in self.line_ids if line.alternator_serial_id)
        twice = [record.name for record, count in list(lots.items()) + list(alternators.items()) if count > 1]
        if twice:
            raise UserError(_("Chosen for two generators: %s", ", ".join(twice)))
        result = True
        for line in self.line_ids:
            res = line.action_confirm()
            if isinstance(res, dict) and result is True:
                result = res
        return result if isinstance(result, dict) else {"type": "ir.actions.act_window_close"}
