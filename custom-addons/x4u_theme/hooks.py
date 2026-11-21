def post_init_hook(env):
    set_home_action(env)


def set_home_action(env):
    """The Home page is the start page of every internal user who has none, and of new users.
    A start page someone chose (Settings > Users > Home Action) is kept."""
    action = env.ref("x4u_theme.action_x4u_home")
    users = env["res.users"].with_context(active_test=False).search([("share", "=", False), ("action_id", "=", False)])
    users.write({"action_id": action.id})
    env["ir.default"].set("res.users", "action_id", action.id)
