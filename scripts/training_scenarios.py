"""Training database only: seven linked orders, each stopped at a different stage, so every
role finds work waiting for it (after scripts/training_data.py).

    docker compose run --rm -T web odoo shell -d odoo4u_training --no-http < scripts/training_scenarios.py

Each step is done by the user of its role, like in real life: shamsa (Salesperson),
"ahmed gamal" (Accountant), tareq (Purchasing & Storekeeper), yasser (Operation Manager).
Customer PO references TRN-PO-1..7. Runs once (x4u_training.scenarios); refuses any
database whose name does not end in _training.
"""

import base64

from odoo import Command, fields

if not env.cr.dbname.endswith("_training"):
    raise SystemExit("training_scenarios.py runs on a *_training database only, not on %r." % env.cr.dbname)
Params = env["ir.config_parameter"].sudo()
if Params.get_param("x4u_training.scenarios"):
    raise SystemExit("The training orders were made already (%s)." % Params.get_param("x4u_training.scenarios"))


def user(login):
    found = env["res.users"].search([("login", "=", login)])
    if not found:
        raise SystemExit("No user %r in this database." % login)
    return found


S, ACC, PUR, OM = user("shamsa"), user("ahmed gamal"), user("tareq"), user("yasser")
TERM = env["account.payment.term"].search([("name", "ilike", "50")], limit=1) or env.ref("account.account_payment_term_immediate")
REPORT = []


def variant(code):
    return env["product.product"].search([("default_code", "=", code)])


def customer(name):
    return env["res.partner"].search([("name", "=", name + " (Training)")])


def pdf(by, name, order):
    return env["ir.attachment"].with_user(by).create(
        {"name": name, "datas": base64.b64encode(b"%PDF-1.4 training"), "res_model": "sale.order", "res_id": order.id}
    )


def quote(partner, code, qty):
    return env["sale.order"].with_user(S).create(
        {
            "partner_id": customer(partner).id,
            "payment_term_id": TERM.id,
            "order_line": [Command.create({"product_id": variant(code).id, "product_uom_qty": qty, "x4u_supply": "assemble"})],
        }
    )


def create_pi(order):
    order.with_user(S).action_x4u_create_proforma()


def send_to_accountant(order, ref):
    order = order.with_user(S)
    order.write(
        {
            "client_order_ref": ref,
            "x4u_lpo_date": fields.Date.today(),
            "x4u_lpo_attachment_ids": [Command.set(pdf(S, ref + ".pdf", order).ids)],
            "x4u_payment_proof_ids": [Command.link(pdf(S, ref + "-transfer.pdf", order).id)],
        }
    )
    order.action_x4u_send_to_accountant()


def confirm_with_advance(order):
    order = order.with_user(ACC)
    order.action_x4u_po_match()
    action = order.action_x4u_register_payment()
    env["account.payment"].with_user(ACC).browse(action["res_id"]).action_post()
    env.invalidate_all()
    order.action_confirm()


def job(order):
    return order.x4u_job_ids[:1]


def request_lines(order):
    return job(order).production_ids._x4u_purchase_requests().line_ids.filtered(lambda line: not line.cancelled)


def job_pos(order):
    """The purchase orders of the Job Order's parts (their origin is a manufacturing order)."""
    names = job(order).production_ids.mapped("name")
    return env["purchase.order"].search([("origin", "in", names)]) if names else env["purchase.order"]


def make_rfqs(order):
    """Tareq turns the material requests into RFQs, one per vendor of the part."""
    lines = request_lines(order)
    Wizard = env["purchase.request.line.make.purchase.order"].with_user(PUR)
    for vendor in lines.product_id.seller_ids.partner_id:
        selected = lines.filtered(lambda line, v=vendor: line.product_id.seller_ids[:1].partner_id == v)
        if selected:
            Wizard.with_context(active_model="purchase.request.line", active_ids=selected.ids).create(
                {"supplier_id": vendor.id}
            ).make_purchase_order()
    pos = job_pos(order)
    for line in pos.order_line:
        line.price_unit = line.product_id.standard_price
    return pos


def deliver_materials(order):
    action = job(order).with_user(PUR).action_deliver_materials()
    wizard = env[action["res_model"]].with_user(PUR).browse(action["res_id"])
    used = {"e": set(), "b": set(), "a": set()}
    for line in wizard.line_ids:
        vals = {}
        if not line.engine_lot_id and line.engine_move_id:
            vals["engine_lot_id"] = line.available_engine_lot_ids.filtered(lambda l: l.id not in used["e"])[:1].id
        if not line.body_lot_id and line.body_move_id:
            vals["body_lot_id"] = line.available_body_lot_ids.filtered(lambda l: l.id not in used["b"])[:1].id
        if not line.alternator_serial_id and line.alternator_move_id:
            vals["alternator_serial_id"] = line.available_alternator_ids.filtered(lambda l: l.id not in used["a"])[:1].id
        if vals:
            line.write(vals)
        used["e"].add(line.engine_lot_id.id)
        used["b"].add(line.body_lot_id.id)
        used["a"].add(line.alternator_serial_id.id)
    wizard.action_confirm()


def finish(order):
    action = job(order).with_user(OM).action_finish()
    env[action["res_model"]].with_user(OM).browse(action["res_id"]).action_confirm()


def scenario(number, title, steps, next_step):
    try:
        with env.cr.savepoint():
            order = steps()
        env.cr.commit()
        pos = job_pos(order)
        REPORT.append(
            "OK   %s %s | %s %s | job %s %s | POs %s | next: %s"
            % (number, title, order.name, order.state, job(order).name or "-", job(order).state or "",
               ", ".join("%s %s" % (p.name, p.state) for p in pos) or "-", next_step)
        )
    except Exception as exc:  # noqa: BLE001 - one failed story must not stop the others
        env.cr.rollback()
        env.invalidate_all()
        REPORT.append("FAIL %s %s | %s: %s" % (number, title, type(exc).__name__, str(exc).replace("\n", " ")[:300]))


def s7():
    order = quote("Al Noor Contracting", "TR-G250-OA", 1)
    create_pi(order)
    send_to_accountant(order, "TRN-PO-7")
    confirm_with_advance(order)
    deliver_materials(order)
    finish(order)
    return order


def s4():
    order = quote("Emirates Facilities Management", "TR-G250-CA", 3)
    create_pi(order)
    send_to_accountant(order, "TRN-PO-4")
    confirm_with_advance(order)
    return order


def s5():
    order = quote("Sahara Projects LLC", "TR-G500-OL", 3)
    create_pi(order)
    send_to_accountant(order, "TRN-PO-5")
    confirm_with_advance(order)
    for po in make_rfqs(order):
        po.with_user(PUR).button_confirm()
    return order


def s6():
    order = quote("Al Noor Contracting", "TR-G100-CA", 3)
    create_pi(order)
    send_to_accountant(order, "TRN-PO-6")
    confirm_with_advance(order)
    for po in make_rfqs(order):
        po.with_user(PUR).button_confirm()
        if po.state == "to approve":
            po.with_user(OM).button_approve()
    return order


def s3():
    order = quote("Sahara Projects LLC", "TR-G500-CA", 1)
    create_pi(order)
    send_to_accountant(order, "TRN-PO-3")
    return order


def s2():
    order = quote("Emirates Facilities Management", "TR-G250-OL", 1)
    create_pi(order)
    return order


def s1():
    return quote("Al Noor Contracting", "TR-G100-OA", 1)


# The order matters for the stock: the finished generator takes its parts first.
scenario(7, "finished generator", s7, "Ahmed: 2nd payment + Create Tax Invoice; Tareq: Deliver Generators")
scenario(4, "Job Order waiting for parts", s4, "Tareq: RFQs from the material requests")
scenario(5, "purchase order to approve", s5, "Yasser: approve the POs; Tareq: receive")
scenario(6, "purchase approved, receipt waiting", s6, "Tareq: receive with serials, Deliver Materials")
scenario(3, "sent to the accountant", s3, "Ahmed: PO Matches, Register Payment, Confirm")
scenario(2, "PI issued", s2, "Shamsa: customer PO + transfer receipt, Send to Accountant")
scenario(1, "draft quotation", s1, "Shamsa: Create PI, send to the customer")

if not any(line.startswith("FAIL") for line in REPORT):
    Params.set_param("x4u_training.scenarios", fields.Datetime.now().strftime("%Y-%m-%d %H:%M"))
    env.cr.commit()
print("TRAINING-REPORT-BEGIN")
for line in sorted(REPORT, key=lambda l: int(l.split()[1])):
    print(line)
print("TRAINING-REPORT-END")
