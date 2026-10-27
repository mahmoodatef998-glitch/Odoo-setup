from odoo import Command

# One pricelist per currency: prices are entered by hand (docs/modules/01-sales.md D2).
PRICELISTS = {
    "pricelist_standard": "Standard",
    "pricelist_export": "Export",
}


def remove_default_pricelist(env):
    """Keep only our pricelists.

    Enabling pricelists makes Odoo create a "Default" one and re-activate it on
    every Settings save. Our pricelists belong to the company, so Standard takes
    that role, and any other rule-less company pricelist (Odoo's Default, or the
    Contractors / Distributors ones of 18.0.1.0.1) goes while no sales order uses it.
    """
    Pricelist = env["product.pricelist"].with_context(active_test=False)
    ours = Pricelist.browse([env.ref("x4u_setup_4u." + xmlid).id for xmlid in PRICELISTS])
    extra = Pricelist.search(
        [("id", "not in", ours.ids), ("company_id", "in", ours.company_id.ids), ("item_ids", "=", False)]
    )
    extra -= env["sale.order"].with_context(active_test=False).search([("pricelist_id", "in", extra.ids)]).pricelist_id
    extra.unlink()


SERVICES = ("product_installation", "product_transport", "product_commissioning")


def use_sharjah_sales_tax(env):
    """Default sales tax 5% Sharjah until the accountant decides (01-sales.md D12).

    The UAE chart makes the first emirate's tax (Abu Dhabi) the default, and the
    products created so far took it, so they move to Sharjah too. Our services
    get it as well when they were created before the chart and have no tax.
    """
    company = env.company
    sharjah = env.ref("account.%s_uae_sale_tax_5_sharjah" % company.id, raise_if_not_found=False)
    if not sharjah:
        return
    old = company.account_sale_tax_id
    if old != sharjah:
        company.account_sale_tax_id = sharjah
        if old:
            products = env["product.template"].with_context(active_test=False).search([("taxes_id", "in", old.ids)])
            products.write({"taxes_id": [Command.unlink(old.id), Command.link(sharjah.id)]})
    for xmlid in SERVICES:
        template = env.ref("x4u_setup_4u." + xmlid).product_tmpl_id
        if not template.taxes_id.filtered(lambda tax: tax.company_id == company):
            template.taxes_id = [Command.link(sharjah.id)]


DOCUMENT_PREFIX = "4U"  # invoices 4U-INV-2026-0001 (docs/modules/06-accounting.md)
NUMBERING = {"sale.order": "S", "purchase.order": "PO"}


def set_numbering(env):
    """Sales S001, purchases PO001, Job Orders MO001 (x4u_job_order spec v0.4 V1).

    Only the prefix and the padding change, so a database in use keeps counting.
    """
    company = env.company
    for code, prefix in NUMBERING.items():
        env["ir.sequence"].search([("code", "=", code), ("company_id", "in", [company.id, False])]).write(
            {"prefix": prefix, "padding": 3}
        )
    warehouse = env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
    warehouse.manu_type_id.sequence_id.write({"prefix": "MO", "padding": 3})


def post_init_hook(env):
    """4U numbering and generator flow (docs/specs/x4u_setup_sales.md §7)."""
    remove_default_pricelist(env)
    use_sharjah_sales_tax(env)
    company = env.company
    company.write(
        {
            "quotation_validity_days": 30,
            "sale_order_template_id": env.ref("x4u_setup_4u.template_generator_supply").id,
            "x4u_document_prefix": DOCUMENT_PREFIX,
        }
    )
    warehouse = env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
    # "Pick Components" is the Material Delivered step (blueprint J8).
    warehouse.manufacture_steps = "pbm"
    set_numbering(env)
    # Every sale opens a Job Order (pure MTO to the customer), while components
    # come from stock when there, else they are ordered for the Job Order (J3).
    env.ref("stock.route_warehouse0_mto").active = True
    warehouse.pbm_mto_pull_id.procure_method = "mts_else_mto"
    env.ref("sales_team.team_sales_department").name = "4U Sales"
