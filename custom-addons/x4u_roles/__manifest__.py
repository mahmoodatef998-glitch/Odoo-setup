# Copyright 2026 4U Power Generation FZC
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "4U Roles",
    "summary": "One role per job (Salesperson, Storekeeper, General Manager...): "
    "the admin gives each user one role and gets the right permissions",
    "version": "18.0.1.0.1",
    "category": "Hidden",
    # AGPL-3 because it depends on quality_control_oca (AGPL-3).
    "license": "AGPL-3",
    "author": "4U Power Generation FZC",
    "depends": [
        "base_user_role",
        "sale_management",
        "purchase_request",
        "mrp",
        "quality_control_oca",
        # Accounting, Time Off and payroll are part of the General Manager / Accountant roles.
        "hr_holidays",
        "payroll",
    ],
    "data": [
        "data/res_users_role_data.xml",
    ],
    "installable": True,
}
