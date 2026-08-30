from sqlalchemy import CheckConstraint

from app.models.catalog import Category, Product, ProductVariant, product_categories


def test_category_model_exposes_hierarchical_publication_fields():
    assert Category.__tablename__ == "categories"
    columns = Category.__table__.c

    assert {"id", "name", "slug", "parent_id", "is_active", "sort_order"} <= set(columns.keys())
    assert columns.parent_id.nullable is True
    assert any(
        constraint.name == "ck_categories_name_not_blank"
        for constraint in Category.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    )
    assert any(
        index.name == "uq_categories_slug_ci" and index.unique
        for index in Category.__table__.indexes
    )


def test_category_parent_foreign_key_sets_parent_to_null_on_delete():
    foreign_keys = list(Category.__table__.c.parent_id.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "categories.id"
    assert foreign_keys[0].ondelete == "SET NULL"


def test_product_model_separates_catalog_identity_from_sellable_variant_data():
    assert Product.__tablename__ == "products"
    columns = Product.__table__.c

    assert {
        "id",
        "name",
        "slug",
        "brand",
        "description",
        "is_alcoholic",
        "abv_percent",
        "is_active",
    } <= set(columns.keys())
    assert "price" not in columns
    assert "inventory" not in columns
    assert any(
        index.name == "uq_products_slug_ci" and index.unique for index in Product.__table__.indexes
    )


def test_product_variant_has_unique_sku_and_product_cascade():
    assert ProductVariant.__tablename__ == "product_variants"
    columns = ProductVariant.__table__.c

    assert {"id", "product_id", "sku", "name", "quantity_value", "quantity_unit"} <= set(
        columns.keys()
    )
    foreign_keys = list(columns.product_id.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "products.id"
    assert foreign_keys[0].ondelete == "CASCADE"
    assert any(
        index.name == "uq_product_variants_sku_ci" and index.unique
        for index in ProductVariant.__table__.indexes
    )


def test_product_category_membership_uses_a_composite_key():
    assert product_categories.primary_key.columns.keys() == ["product_id", "category_id"]
    foreign_keys = {
        foreign_key.target_fullname: foreign_key for foreign_key in product_categories.foreign_keys
    }
    assert foreign_keys["products.id"].ondelete == "CASCADE"
    assert foreign_keys["categories.id"].ondelete == "CASCADE"
