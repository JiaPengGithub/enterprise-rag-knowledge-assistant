from app.storage.database import dumps, get_connection, loads, row_to_dict, rows_to_dicts


DEMO_USERS = [
    {"id": "hr_user", "display_name": "HR Specialist", "department": "Human Resources", "roles": ["employee", "hr"]},
    {"id": "it_user", "display_name": "IT Support Engineer", "department": "IT", "roles": ["employee", "it"]},
    {"id": "pm_user", "display_name": "Project Manager", "department": "Product", "roles": ["employee", "project"]},
    {"id": "admin", "display_name": "Knowledge Admin", "department": "Operations", "roles": ["employee", "admin"]},
]


def seed_users() -> None:
    with get_connection() as connection:
        for user in DEMO_USERS:
            connection.execute(
                """
                INSERT INTO users (id, display_name, department, roles)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    display_name = excluded.display_name,
                    department = excluded.department,
                    roles = excluded.roles
                """,
                (user["id"], user["display_name"], user["department"], dumps(user["roles"])),
            )


def list_users() -> list[dict]:
    with get_connection() as connection:
        rows = rows_to_dicts(connection.execute("SELECT * FROM users ORDER BY id").fetchall())
    for row in rows:
        row["roles"] = loads(row["roles"], [])
    return rows


def get_user(user_id: str) -> dict | None:
    with get_connection() as connection:
        row = row_to_dict(connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    if row:
        row["roles"] = loads(row["roles"], [])
    return row
