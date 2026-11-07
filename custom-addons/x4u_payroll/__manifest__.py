# Copyright 2026 4U Power Generation FZC
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "4U Payroll (UAE)",
    "summary": "UAE salary structure: basic + housing + transport + other allowance, advances and unpaid days, "
    "net pay to Accrued Salaries, and the monthly End of Service, leave salary and air ticket provisions",
    "version": "18.0.1.0.0",
    "category": "Payroll",
    # AGPL-3 because it depends on hr_employee_service and x4u_account (AGPL-3).
    "license": "AGPL-3",
    "author": "4U Power Generation FZC",
    "depends": [
        "payroll_account",
        # Housing, transport, other allowance and air ticket amounts per contract.
        "payroll_contract_advantages",
        # The service start date for the End of Service days (21 / 30).
        "hr_employee_service",
        # The accounts, found by code (4U / ATA chart).
        "x4u_account",
    ],
    "data": [
        "data/x4u_payroll_data.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
