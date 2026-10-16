"""identity and tenancy tables

Revision ID: 432e25bf4059
Revises: 850e0fe11594
Create Date: 2026-10-16 09:34:44.385662

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "432e25bf4059"
down_revision: str | Sequence[str] | None = "850e0fe11594"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # citext = case-insensitive text; users.email uses it. Not dropped on downgrade, because
    # other tables in later migrations may use it too.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "plans",
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("max_active_jobs", sa.Integer(), nullable=False),
        sa.Column("max_staff_seats", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("max_active_jobs > 0", name=op.f("ck_plans_jobs_positive")),
        sa.CheckConstraint("max_staff_seats > 0", name=op.f("ck_plans_seats_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plans")),
        sa.UniqueConstraint("name", name=op.f("uq_plans_name")),
    )
    op.create_table(
        "users",
        sa.Column("external_id", sa.String(length=64), nullable=True),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("is_platform_admin", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("external_id", name=op.f("uq_users_external_id")),
    )
    op.create_table(
        "companies",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "suspended",
                name="company_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            server_default="active",
            nullable=False,
        ),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("time_zone", sa.String(length=64), nullable=False),
        sa.Column("retention_months", sa.Integer(), nullable=True),
        sa.Column("brand_color", sa.String(length=7), nullable=True),
        sa.Column("logo_blob_name", sa.String(length=300), nullable=True),
        sa.Column("careers_intro", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_companies_currency_format")),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_companies_slug_format")
        ),
        # (the status check comes from sa.Enum(create_constraint=True) on the column above)
        sa.CheckConstraint(
            "retention_months IS NULL OR retention_months > 0",
            name=op.f("ck_companies_retention_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], name=op.f("fk_companies_plan_id_plans"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
        sa.UniqueConstraint("slug", name=op.f("uq_companies_slug")),
    )
    op.create_table(
        "staff_members",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "is_active OR deactivated_at IS NOT NULL",
            name=op.f("ck_staff_members_deactivated_has_time"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_staff_members_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_staff_members_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_members")),
        sa.UniqueConstraint("id", "company_id", name="uq_staff_members_id_company_id"),
        sa.UniqueConstraint("user_id", name=op.f("uq_staff_members_user_id")),
    )
    op.create_index(
        op.f("ix_staff_members_company_id"), "staff_members", ["company_id"], unique=False
    )
    op.create_table(
        "staff_roles",
        sa.Column("staff_member_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "company_admin",
                "recruiter",
                "hiring_manager",
                "interviewer",
                name="staff_role",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        # (the role check comes from sa.Enum(create_constraint=True) on the column above)
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_staff_roles_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["staff_member_id", "company_id"],
            ["staff_members.id", "staff_members.company_id"],
            name="fk_staff_roles_staff_member_company",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("staff_member_id", "role", name=op.f("pk_staff_roles")),
    )
    op.create_index(op.f("ix_staff_roles_company_id"), "staff_roles", ["company_id"], unique=False)

    # The three subscription tiers every environment needs. ids come from gen_random_uuid().
    plans = sa.table(
        "plans",
        sa.column("name", sa.String),
        sa.column("max_active_jobs", sa.Integer),
        sa.column("max_staff_seats", sa.Integer),
    )
    op.bulk_insert(
        plans,
        [
            {"name": "Free", "max_active_jobs": 2, "max_staff_seats": 3},
            {"name": "Pro", "max_active_jobs": 10, "max_staff_seats": 15},
            {"name": "Business", "max_active_jobs": 50, "max_staff_seats": 100},
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_staff_roles_company_id"), table_name="staff_roles")
    op.drop_table("staff_roles")
    op.drop_index(op.f("ix_staff_members_company_id"), table_name="staff_members")
    op.drop_table("staff_members")
    op.drop_table("companies")
    op.drop_table("users")
    op.drop_table("plans")
