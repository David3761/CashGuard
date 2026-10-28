"""Operations Alembic's autogenerate can't detect. Use them inside a migration's upgrade()."""

from enum import StrEnum

from alembic import op

from app.db.models import enum_in


def replace_enum_check(table: str, column: str, enum: type[StrEnum]) -> None:
    """Rewrite the `ck_<table>_<column>` CHECK after values were added to / removed from `enum`.

    Example (a new Category value):
        replace_enum_check("transactions", "category", Category)
        replace_enum_check("spending_signatures", "category", Category)
        ...one call per column listed with that enum in models.py
    """
    name = f"ck_{table}_{column}"
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, enum_in(column, enum))
