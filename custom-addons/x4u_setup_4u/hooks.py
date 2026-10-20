def post_init_hook(env):
    """4U numbering and generator flow (docs/specs/x4u_setup_sales.md §7)."""
    company = env.company
    company.write(
        {
            "quotation_validity_days": 30,
            "sale_order_template_id": env.ref("x4u_setup_4u.template_generator_supply").id,
        }
    )
    # Sales order 4U-SO-001; generator Job Order 4U-PO-001 (purchase orders keep P00001).
    env["ir.sequence"].search(
        [("code", "=", "sale.order"), ("company_id", "in", [company.id, False])]
    ).write({"prefix": "4U-SO-", "padding": 3})
    warehouse = env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
    # "Pick Components" is the Material Delivered step (blueprint J8).
    warehouse.manufacture_steps = "pbm"
    warehouse.manu_type_id.sequence_id.write({"prefix": "4U-PO-", "padding": 3})
    # Every sale opens a Job Order (pure MTO to the customer), while components
    # come from stock when there, else they are ordered for the Job Order (J3).
    env.ref("stock.route_warehouse0_mto").active = True
    warehouse.pbm_mto_pull_id.procure_method = "mts_else_mto"
    env.ref("sales_team.team_sales_department").name = "4U Sales"
