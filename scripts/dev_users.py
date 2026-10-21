"""Dev only: one test user per 4U role, fake names on example.com, no password.

The admin sets a password (Settings > Users > Action > Change Password) when
someone needs to log in as one of them. Runs inside "odoo shell" through
scripts/dev-users.ps1 or scripts/create-db.ps1 -TestUsers. Safe to run again.
"""

TEST_USERS = [
    ("x4u.salesperson@example.com", "Test Salesperson", "role_salesperson"),
    ("x4u.salesmanager@example.com", "Test Sales Manager", "role_sales_manager"),
    ("x4u.purchasing@example.com", "Test Purchasing Officer", "role_purchasing_officer"),
    ("x4u.gm@example.com", "Test General Manager", "role_general_manager"),
    ("x4u.store@example.com", "Test Storekeeper", "role_storekeeper"),
    ("x4u.production@example.com", "Test Production", "role_production"),
    ("x4u.quality@example.com", "Test Quality Inspector", "role_quality_inspector"),
    ("x4u.accountant@example.com", "Test Accountant", "role_accountant"),
]
# Who gets the Job Order activities (Settings > Manufacturing > 4U Job Orders).
ACTIVITY_USERS = {
    "purchase": "x4u.purchasing@example.com",
    "warehouse": "x4u.store@example.com",
    "qc": "x4u.quality@example.com",
}

Users = env["res.users"].with_context(active_test=False, no_reset_password=True)
for login, name, role in TEST_USERS:
    user = Users.search([("login", "=", login)], limit=1)
    if not user:
        user = Users.create({"name": name, "login": login, "email": login})
    if not user.role_line_ids:
        user.write({"role_line_ids": [(0, 0, {"role_id": env.ref("x4u_roles." + role).id})]})

def by_login(login):
    return Users.search([("login", "=", login)], limit=1)

team = env.ref("sales_team.team_sales_department")
team.member_ids |= by_login("x4u.salesperson@example.com") | by_login("x4u.salesmanager@example.com")
params = env["ir.config_parameter"].sudo()
for key, login in ACTIVITY_USERS.items():
    params.set_param("x4u_job_order.%s_user_id" % key, by_login(login).id)
env.cr.commit()
for login, name, role in TEST_USERS:
    print("Test user:", name, "|", login, "|", by_login(login).role_ids.name)
