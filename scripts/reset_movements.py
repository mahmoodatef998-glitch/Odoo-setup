"""Clear every movement of a one-company database and keep its setup (the user, 2026-11-25:
start the pilot again after UAT Phases 3-4 and follow the reports with every movement).

Deleted: sales / purchase orders, purchase requests, PIs, receipts / deliveries / transfers, stock,
serials, Job Orders, MOs, generator cards, invoices, bills, payments, PDC deposits, assets, journal
entries, analytic lines, and their chatter, activities and attachments. The numbering starts again
from 1 (PO001, WH/IN/00001, MO001, PI1, 4U-INV-2026-0001...). Products whose cost came from the
deleted stock go back to cost 0.
Kept: users and their passwords, companies, contacts, products and the generator catalog, prices,
BoMs, chart of accounts, journals, taxes, letterhead, terms and every setting.
X4U_RESET_PRODUCT_TMPL_IDS also deletes those product templates (test products), with their BoMs.

Run on the server, after deploy/backup-daily.sh (cd /opt/odoo4u):
  docker compose run --rm -T -e X4U_RESET_DB=odoo4u [-e X4U_RESET_PRODUCT_TMPL_IDS=8,9,10] \
      [-e X4U_RESET_COMMIT=1] web odoo shell -d odoo4u --no-http < scripts/reset_movements.py
Without X4U_RESET_COMMIT=1 it is a dry run: it reports what it would delete and rolls back.
"""
import os

from psycopg2 import errors

DB = os.environ.get("X4U_RESET_DB")
COMMIT = os.environ.get("X4U_RESET_COMMIT") == "1"
PRODUCT_TMPL_IDS = [int(i) for i in os.environ.get("X4U_RESET_PRODUCT_TMPL_IDS", "").split(",") if i.strip()]

# The movements, children first (a table that is still referenced is tried again on the next pass).
MODELS = [
    "account.partial.reconcile", "account.full.reconcile", "account.analytic.line",
    "account.asset.line", "account.asset", "account.check.deposit",
    "account.bank.statement.line", "account.bank.statement",
    "account.payment", "account.move.line", "account.move",
    "stock.valuation.adjustment.lines", "stock.landed.cost.lines", "stock.landed.cost",
    "stock.valuation.layer", "stock.move.line", "stock.scrap", "stock.move", "stock.package_level",
    "stock.quant", "stock.quant.package", "stock.picking",
    "mrp.workorder", "mrp.unbuild", "mrp.production",
    "x4u.generator.hour.reading", "x4u.generator", "x4u.job.order.event", "x4u.job.order",
    "x4u.ready.order", "x4u.alternator.serial", "stock.lot",
    "x4u.purchase.proforma", "x4u.purchase.schedule", "purchase.order.line", "purchase.order",
    "purchase.request.allocation", "purchase.request.line", "purchase.request",
    "x4u.sale.proforma", "x4u.sale.schedule", "sale.order.option", "sale.order.line", "sale.order",
]
# Numbering of these starts again from 1 (with every picking type's own sequence).
SEQUENCE_CODES = [
    "purchase.order", "sale.order", "purchase.request", "stock.lot.serial", "stock.landed.cost",
    "stock.scrap", "stock.quant.package", "mrp.production", "mrp.unbuild",
]

assert DB and env.cr.dbname == DB, "Set X4U_RESET_DB to this database's name (%s)." % env.cr.dbname
assert env["res.company"].sudo().search_count([]) == 1, "More than one company: this script clears them all."
cr = env.cr


def table_counts():
    cr.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    counts = {}
    for (table,) in cr.fetchall():
        cr.execute('SELECT count(*) FROM "%s"' % table)
        counts[table] = cr.fetchone()[0]
    return counts


before = table_counts()
models = [env[name] for name in MODELS if name in env and not env[name]._abstract and not env[name]._transient]
model_names = [m._name for m in models]

# What the deleted stock valued: those products go back to cost 0.
cr.execute("SELECT DISTINCT product_id FROM stock_valuation_layer")
valued_products = [row[0] for row in cr.fetchall()]

# Wizards first: they may point at the records below.
for model in env.registry.values():
    if model._transient and not model._abstract and model._table in before:
        cr.execute('DELETE FROM "%s"' % model._table)

# Chatter, followers, activities and attachments of the movements.
cr.execute("DELETE FROM mail_activity WHERE res_model = ANY(%s)", [model_names])
cr.execute("DELETE FROM mail_followers WHERE res_model = ANY(%s)", [model_names])
cr.execute("DELETE FROM mail_message WHERE model = ANY(%s)", [model_names])
cr.execute("DELETE FROM ir_attachment WHERE res_model = ANY(%s)", [model_names])

pending = list(models)
for _pass in range(len(pending) + 1):
    blocked = []
    for model in pending:
        cr.execute("SAVEPOINT x4u_reset")
        try:
            cr.execute('DELETE FROM "%s"' % model._table)
            cr.execute("RELEASE SAVEPOINT x4u_reset")
        except (errors.ForeignKeyViolation, errors.RestrictViolation):
            cr.execute("ROLLBACK TO SAVEPOINT x4u_reset")
            blocked.append(model)
    if not blocked:
        break
    if len(blocked) == len(pending):
        raise RuntimeError("Still referenced: %s" % ", ".join(m._name for m in blocked))
    pending = blocked
env.invalidate_all()

if valued_products:
    cr.execute("UPDATE product_product SET standard_price = NULL WHERE id = ANY(%s)", [valued_products])
    env.invalidate_all()

# Test products, with their BoMs and vendor prices.
if PRODUCT_TMPL_IDS:
    templates = env["product.template"].sudo().with_context(active_test=False).browse(PRODUCT_TMPL_IDS).exists()
    variants = templates.product_variant_ids
    boms = env["mrp.bom"].sudo().with_context(active_test=False).search(
        ["|", "|", ("product_tmpl_id", "in", templates.ids), ("product_id", "in", variants.ids),
         ("bom_line_ids.product_id", "in", variants.ids)]
    )
    boms.unlink()
    env["product.supplierinfo"].sudo().search([("product_tmpl_id", "in", templates.ids)]).unlink()
    print("Deleted test products: %s" % ", ".join(templates.mapped("display_name")))
    templates.unlink()

sequences = env["ir.sequence"].sudo().search(
    ["|", ("code", "in", SEQUENCE_CODES), ("code", "=like", "x4u.%")]
) | env["stock.picking.type"].sudo().with_context(active_test=False).search([]).sequence_id
if COMMIT:
    # Only when applying: a standard sequence restarts with ALTER SEQUENCE, kept even by a rollback.
    for sequence in sequences:
        sequence.number_next_actual = 1
        for date_range in sequence.date_range_ids:
            date_range.number_next_actual = 1
print("Numbering from 1: %s" % ", ".join(sorted(set(sequences.mapped("name")))))

after = table_counts()
print("Rows deleted, by table:")
for table in sorted(before):
    gone = before[table] - after.get(table, 0)
    if gone:
        print("  %-50s %6d of %6d" % (table, gone, before[table]))
leftover = {t: after[t] for t in (m._table for m in models) if after.get(t)}
assert not leftover, "Left over: %s" % leftover

if COMMIT:
    cr.commit()
    print("COMMITTED")
else:
    cr.rollback()
    print("DRY RUN: nothing changed (set X4U_RESET_COMMIT=1 to apply)")
