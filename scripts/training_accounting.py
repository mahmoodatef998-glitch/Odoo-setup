"""Training database only: a year of 4U accounting on the Focus tree, so every report has something
to show - 20 customers in every situation, suppliers, cheques both ways, cash, salaries, rent, an asset.

    docker compose run --rm -T web odoo shell -d odoo4u_training --no-http < scripts/training_accounting.py

Every partner says "(Training)". Runs once (x4u_training.accounting); refuses any database whose
name does not end in _training. Sales / Purchase lock dates are opened while it posts the past
months and put back after. Prints what each customer owes and the checks the reports must pass.

Customers (invoices with 5% VAT, 30 days):
 C01 paid in full by bank             C11 credit note (return), balance paid less a 100 discount
 C02 half paid                        C12 invoice cancelled by a full credit note
 C03 not due yet                      C13 PDC cheque in hand (dated next month)
 C04 overdue 1-30 days                C14 PDC deposited and cleared by the bank
 C05 overdue 31-60 days               C15 PDC bounced after the deposit: the invoice is open again
 C06 overdue 61-90 days               C16 cash customer, paid at the counter
 C07 overdue 91-120 days              C17 paid 1,000 too much: a credit left
 C08 overdue over 120 days            C18 three invoices, one payment for all
 C09 advance first, invoice after     C19 in US dollars, paid in dollars
 C10 advance only, nothing invoiced   C20 bad debt written off
"""

from datetime import date

from odoo import Command, fields

if not env.cr.dbname.endswith("_training"):
    raise SystemExit("training_accounting.py runs on a *_training database only, not on %r." % env.cr.dbname)
Params = env["ir.config_parameter"].sudo()
if Params.get_param("x4u_training.accounting"):
    raise SystemExit("The training accounting was made already (%s)." % Params.get_param("x4u_training.accounting"))

company = env.ref("base.main_company")
env = env(context=dict(env.context, allowed_company_ids=company.ids, lang="en_US"))  # noqa: F821
company = company.with_env(env)
Account = env["account.account"].with_company(company)
Journal = env["account.journal"].with_company(company)
Move = env["account.move"].with_company(company)
Partner = env["res.partner"]


def acc(code):
    account = Account.search([("code", "=", code), *Account._check_company_domain(company)], limit=1)
    if not account:
        raise SystemExit("No account %s: upgrade x4u_account (the Focus tree) first." % code)
    return account


def journal(kind, code=None):
    domain = [("type", "=", kind), ("company_id", "=", company.id)]
    if code:
        domain.append(("code", "=", code))
    return Journal.search(domain, limit=1)


BANK = journal("bank", "BNK1") or journal("bank")
CASH = journal("cash")
CHK = company.x4u_pdc_received_journal_id
MISC = journal("general", "MISC")
SALE_TAX = env["account.tax"].search([("type_tax_use", "=", "sale"), ("amount", "=", 5), ("company_id", "=", company.id)], limit=1)
BUY_TAX = env["account.tax"].search([("type_tax_use", "=", "purchase"), ("amount", "=", 5), ("company_id", "=", company.id)], limit=1)
TERM30 = env.ref("account.account_payment_term_30days")
USD = env.ref("base.USD")
IN_HAND = CHK.inbound_payment_method_line_ids.filtered(lambda line: line.code == "manual")[:1]
PDC_OUT = BANK.outbound_payment_method_line_ids.filtered(lambda line: line.code == "x4u_pdc")[:1]
if not PDC_OUT:
    method = env.ref("x4u_account.account_payment_method_pdc_out")
    BANK.write({"outbound_payment_method_line_ids": [Command.create({"payment_method_id": method.id, "name": "PDC Cheque"})]})
    PDC_OUT = BANK.outbound_payment_method_line_ids.filtered(lambda line: line.code == "x4u_pdc")[:1]

SALES_GEN, SALES_PARTS, SALES_SERVICE = acc("410002"), acc("410009"), acc("410003")
RECEIVABLE, PAYABLE = acc("133001"), acc("211001")
locks = {"sale_lock_date": company.sale_lock_date, "purchase_lock_date": company.purchase_lock_date}
company.sudo().write({"sale_lock_date": False, "purchase_lock_date": False})


def partner(name, supplier=False, person=False):
    name = "%s (Training)" % name
    found = Partner.search([("name", "=", name)], limit=1)
    if found:
        return found
    return Partner.create({"name": name, "is_company": not person, "country_id": env.ref("base.ae").id,
                           "customer_rank": 0 if supplier or person else 1, "supplier_rank": 1 if supplier else 0})


def d(month, day):
    return date(2026, month, day)


def invoice(customer, day, amount, account=SALES_GEN, label="Diesel generator set", currency=None, kind="out_invoice"):
    move = Move.create({
        "move_type": kind, "partner_id": customer.id, "invoice_date": day, "date": day,
        "invoice_payment_term_id": TERM30.id, "currency_id": (currency or company.currency_id).id,
        "invoice_line_ids": [Command.create({"name": "%s (Training)" % label, "quantity": 1, "price_unit": amount,
                                             "account_id": account.id, "tax_ids": [Command.set(SALE_TAX.ids)]})],
    })
    move.action_post()
    return move


def bill(vendor, day, amount, account, label):
    move = Move.create({
        "move_type": "in_invoice", "partner_id": vendor.id, "invoice_date": day, "date": day, "invoice_payment_term_id": TERM30.id,
        "invoice_line_ids": [Command.create({"name": "%s (Training)" % label, "quantity": 1, "price_unit": amount,
                                             "account_id": account.id, "tax_ids": [Command.set(BUY_TAX.ids)]})],
    })
    move.action_post()
    return move


def pay(moves, day, amount=None, jrnl=BANK, method=None, difference=None, cheque=None):
    values = {"journal_id": jrnl.id, "payment_date": day}
    if amount is not None:
        values["amount"] = amount
    if method:
        values["payment_method_line_id"] = method.id
    if cheque:
        values.update({"x4u_cheque_number": cheque[0], "x4u_cheque_date": cheque[1]})
    if difference:
        values.update({"payment_difference_handling": "reconcile", "writeoff_account_id": difference[0].id,
                       "writeoff_label": difference[1]})
    wizard = env["account.payment.register"].with_context(active_model="account.move", active_ids=moves.ids).create(values)
    if len(moves) > 1:
        wizard.group_payment = True
    return wizard._create_payments()


def advance(who, day, amount, inbound=True):
    payment = env["account.payment"].create({
        "payment_type": "inbound" if inbound else "outbound", "partner_type": "customer" if inbound else "supplier",
        "partner_id": who.id, "amount": amount, "date": day, "journal_id": BANK.id,
    })
    payment.action_post()
    return payment


def reconcile(account, *records):
    lines = env["account.move.line"]
    for record in records:
        move = record.move_id if record._name == "account.payment" else record
        lines |= move.line_ids
    lines.filtered(lambda line: line.account_id == account and not line.reconciled).reconcile()


def entry(day, lines, jrnl=MISC, ref=None):
    move = Move.create({"move_type": "entry", "journal_id": jrnl.id, "date": day, "ref": ref,
                        "line_ids": [Command.create({"account_id": a.id, "name": label, "partner_id": p.id if p else False,
                                                     "debit": max(amt, 0.0), "credit": max(-amt, 0.0)})
                                     for a, amt, label, p in lines]})
    move.action_post()
    return move


def bank_clears(payment, day):
    """What the bank reconciliation does when the bank pays (or takes) the cheque."""
    if payment.payment_type == "inbound":
        line = payment.x4u_deposit_line_ids
    else:
        line = payment.move_id.line_ids.filtered(lambda l: l.account_id == payment.outstanding_account_id)
    amount = line.balance
    move = entry(day, [(BANK.default_account_id, amount, "Bank: cheque %s" % payment.x4u_cheque_number, None),
                       (line.account_id, -amount, "Cheque %s cleared" % payment.x4u_cheque_number, line.partner_id)], jrnl=BANK)
    (line + move.line_ids.filtered(lambda l: l.account_id == line.account_id)).reconcile()


def deposit(payments, day):
    dep = env["account.check.deposit"].create({"journal_id": CHK.id, "bank_journal_id": BANK.id, "deposit_date": day})
    dep.get_all_checks()
    dep.check_payment_ids.filtered(lambda l: l.payment_id not in payments).check_deposit_id = False
    dep.validate_deposit()
    return dep


# 0. The owners' capital, the bank opening
entry(d(1, 1), [(BANK.default_account_id, 1500000.0, "Capital paid in", None), (acc("240006"), -1500000.0, "Capital In Paid", None)],
      jrnl=BANK, ref="Capital (Training)")

# 1. Customers ------------------------------------------------------------------------------------
C = {n: partner(name) for n, name in enumerate([
    "Coral Bay Resorts", "Mangrove Engineering", "Dune Valley Farms", "Gulf Marine Services",
    "Desert Rose Hotels", "Falcon Logistics", "Oasis Farms", "Blue Wave Construction", "Pearl Towers Developers",
    "Horizon Schools Group", "Golden Sands Mall", "Al Reem Hospital", "Crescent Steel Industries", "Palm Oil Mills",
    "Arabian Data Center", "Walk-in Cash Customer", "Skyline Elevators", "Northern Cement", "Global Rigs (USD)",
    "Mirage Events"], 1)}
inv = {}
inv[1] = invoice(C[1], d(1, 15), 50000)
pay(inv[1], d(2, 10))
inv[2] = invoice(C[2], d(10, 5), 80000)
pay(inv[2], d(10, 20), amount=42000)
inv[3] = invoice(C[3], d(11, 15), 64000)
inv[4] = invoice(C[4], d(10, 10), 36000, SALES_SERVICE, "Generator maintenance contract")
inv[5] = invoice(C[5], d(9, 10), 58000)
inv[6] = invoice(C[6], d(8, 10), 27000, SALES_PARTS, "Spare parts")
inv[7] = invoice(C[7], d(7, 5), 41000)
inv[8] = invoice(C[8], d(3, 1), 23000)
adv9 = advance(C[9], d(6, 1), 105000)
inv[9] = invoice(C[9], d(7, 1), 100000)
reconcile(RECEIVABLE, adv9, inv[9])
advance(C[10], d(11, 1), 25000)
inv[11] = invoice(C[11], d(4, 10), 60000)
refund11 = invoice(C[11], d(5, 5), 10000, label="Returned canopy", kind="out_refund")
reconcile(RECEIVABLE, inv[11], refund11)
pay(inv[11], d(5, 20), amount=52400, difference=(acc("421002"), "Discount on settlement"))
inv[12] = invoice(C[12], d(6, 15), 30000)
refund12 = invoice(C[12], d(6, 20), 30000, label="Order cancelled", kind="out_refund")
reconcile(RECEIVABLE, inv[12], refund12)
inv[13] = invoice(C[13], d(11, 1), 47000)
pay(inv[13], d(11, 10), jrnl=CHK, method=IN_HAND, cheque=("TR-100013", d(12, 15)))
inv[14] = invoice(C[14], d(9, 1), 39000)
pdc14 = pay(inv[14], d(9, 5), jrnl=CHK, method=IN_HAND, cheque=("TR-100014", d(10, 1)))
deposit(pdc14, d(10, 1))
bank_clears(pdc14, d(10, 3))
inv[15] = invoice(C[15], d(8, 1), 33000)
pdc15 = pay(inv[15], d(8, 3), jrnl=CHK, method=IN_HAND, cheque=("TR-100015", d(9, 1)))
deposit(pdc15, d(9, 1))
pdc15._x4u_pdc_bounce("Insufficient funds (Training)")
inv[16] = invoice(C[16], d(2, 20), 3500, SALES_PARTS, "Battery and filters")
pay(inv[16], d(2, 20), jrnl=CASH)
inv[17] = invoice(C[17], d(5, 10), 20000, SALES_SERVICE, "Installation")
pay(inv[17], d(5, 25), amount=22000)
batch = invoice(C[18], d(6, 1), 15000) | invoice(C[18], d(6, 15), 12000, SALES_PARTS, "Spare parts") \
    | invoice(C[18], d(7, 1), 9000, SALES_SERVICE, "Service visit")
pay(batch, d(7, 20))
inv[19] = invoice(C[19], d(7, 15), 10000, currency=USD)
pay(inv[19], d(8, 15))
inv[20] = invoice(C[20], d(1, 5), 7500, SALES_PARTS, "Spare parts")
writeoff = entry(d(11, 20), [(acc("530084"), 7875.0, "Bad debt written off", None), (RECEIVABLE, -7875.0, "Bad debt written off", C[20])],
                 ref="Bad debt (Training)")
reconcile(RECEIVABLE, inv[20], writeoff)

# 2. Suppliers ------------------------------------------------------------------------------------
V = {key: partner(name, supplier=True) for key, name in [
    ("engines", "Gulf Engines Trading"), ("office", "Office Supplies Co"), ("canopy", "Canopy Works LLC"),
    ("alternators", "Alternator Supplies FZE"), ("steel", "Steel Fabrication LLC"), ("sewa", "SEWA Utilities"),
    ("landlord", "Sharjah Properties"), ("motors", "Al Futtaim Motors")]}
b1 = bill(V["engines"], d(1, 20), 40000, acc("134004"), "Diesel engines")
pay(b1, d(2, 20))
bill(V["office"], d(9, 5), 2000, acc("530050"), "Stationery and printing")
b3 = bill(V["canopy"], d(8, 1), 30000, acc("134004"), "Soundproof canopies")
pdc_out3 = pay(b3, d(8, 5), method=PDC_OUT, cheque=("TR-900003", d(9, 5)))
bank_clears(pdc_out3, d(9, 5))
b4 = bill(V["alternators"], d(10, 15), 25000, acc("134004"), "Alternators")
pay(b4, d(10, 20), method=PDC_OUT, cheque=("TR-900004", d(12, 20)))
advance(V["steel"], d(11, 1), 10000, inbound=False)
for month in range(1, 11):
    sewa = bill(V["sewa"], d(month, 25), 1200, acc("530064"), "Water and electricity %02d/2026" % month)
    pay(sewa, d(month, 28))
rent = bill(V["landlord"], d(1, 2), 120000, acc("137004"), "Office and warehouse rent 2026")
pdc_rent = pay(rent, d(1, 2), method=PDC_OUT, cheque=("TR-900001", d(1, 10)))
bank_clears(pdc_rent, d(1, 10))
truck = bill(V["motors"], d(3, 1), 90000, acc("140001"), "Delivery pick-up truck")
pay(truck, d(3, 15))

# 3. Each month: rent used, salaries, petty cash, bank charges -------------------------------------
staff = [partner(name, person=True) for name in ("Workshop Technician", "Storekeeper", "Sales Engineer")]
salaries = [9000.0, 7000.0, 12000.0]
entry(d(1, 5), [(CASH.default_account_id, 6000.0, "Petty cash from the bank", None),
                (BANK.default_account_id, -6000.0, "Petty cash from the bank", None)], jrnl=CASH, ref="Petty cash (Training)")
for month in range(1, 12):
    last = fields.Date.end_of(d(month, 1), "month")
    entry(last, [(acc("530053"), 10000.0, "Rent %02d/2026" % month, None),
                 (acc("137004"), -10000.0, "Rent %02d/2026" % month, None)], ref="Rent used (Training)")
    lines = [(acc("510001"), amount, "Salary %02d/2026" % month, person) for person, amount in zip(staff, salaries)]
    lines += [(acc("215003"), -amount, "Salary %02d/2026" % month, person) for person, amount in zip(staff, salaries)]
    accrual = entry(last, lines, ref="Salaries (Training)")
    if month < 11:
        paid = entry(d(month + 1, 3),
                     [(acc("215003"), amount, "Salary paid %02d/2026" % month, person) for person, amount in zip(staff, salaries)]
                     + [(BANK.default_account_id, -sum(salaries), "Salaries paid %02d/2026" % month, None)], jrnl=BANK,
                     ref="Salaries paid (Training)")
        reconcile(acc("215003"), accrual, paid)
    entry(d(month, 18), [(acc("530030"), 350.0, "Kitchen", None), (acc("530046"), 900.0, "Petrol", None),
                         (acc("530031"), 250.0, "Taxi", None), (CASH.default_account_id, -1500.0, "Petty cash expenses", None)],
          jrnl=CASH, ref="Petty cash (Training)")
    if month % 4 == 0:
        entry(d(month, 19), [(CASH.default_account_id, 6000.0, "Petty cash top-up", None),
                             (BANK.default_account_id, -6000.0, "Petty cash top-up", None)], jrnl=CASH, ref="Petty cash (Training)")
    entry(last, [(acc("530048"), 52.5, "Bank charges", None), (BANK.default_account_id, -52.5, "Bank charges", None)],
          jrnl=BANK, ref="Bank charges (Training)")

# 4. The truck: its asset card, depreciated every month up to now --------------------------------
asset_note = "no asset card"
asset = env["account.asset"].search([("account_move_line_ids.move_id", "=", truck.id)], limit=1)
if asset:
    if asset.state == "draft":
        asset.validate()
    asset.compute_depreciation_board()
    for line in asset.depreciation_line_ids.filtered(lambda l: l.type == "depreciate" and not l.move_check and l.line_date <= d(11, 30)):
        line.create_move()
    asset_note = "%s, %d months depreciated" % (asset.name, len(asset.depreciation_line_ids.filtered("move_check")))

company.sudo().write(locks)
Params.set_param("x4u_training.accounting", fields.Datetime.now().strftime("%Y-%m-%d %H:%M"))
env.cr.commit()

# 5. What each customer owes now -------------------------------------------------------------------
env.invalidate_all()
print("TRAINING-ACCOUNTING-BEGIN")
for n, customer in C.items():
    lines = env["account.move.line"].search([("partner_id", "=", customer.id), ("account_id", "=", RECEIVABLE.id), ("parent_state", "=", "posted")])
    open_lines = lines.filtered(lambda l: not l.reconciled)
    print("C%02d %-40s balance %12s  open items %d" % (n, customer.name[:40], "{:,.2f}".format(sum(lines.mapped("balance"))), len(open_lines)))
print("asset:", asset_note)
print("lock dates back:", company.sale_lock_date, company.purchase_lock_date)
print("TRAINING-ACCOUNTING-END")
