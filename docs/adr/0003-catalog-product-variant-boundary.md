# ADR 0003: Separate catalog products from sellable variants

- Status: Accepted
- Date: 2026-08-26
- Scope: Phase 3 catalog foundation

## Decision

Represent the catalog using four persistence concepts:

1. `categories` — hierarchical merchandising taxonomy;
2. `products` — customer-facing identity and classification;
3. `product_categories` — many-to-many merchandising membership;
4. `product_variants` — sellable SKU and package quantity identity.

Expose only read-only public catalog endpoints in this phase. Product and
variant mutation requires a later admin boundary with authorization, auditing,
and publication workflow.

## Reason

A beverage product can have multiple package sizes and barcodes, while each
package is the unit that inventory and pricing will eventually address. Keeping
product identity separate from the sellable variant avoids putting prices or
stock on a product row and prevents future inventory allocation from being
coupled to merchandising descriptions.

Many-to-many category membership supports an item appearing in both a primary
beverage aisle and a cross-merchandised party collection without duplicating
product records. A parent-linked category table supports nested aisles while
keeping the initial API payload compact and client-friendly.

## Alternatives considered

### One product row per SKU

Rejected. It duplicates descriptions, brand data, and alcohol classification
across package sizes and makes catalog edits inconsistent.

### One category foreign key on products

Rejected. Cross-merchandising is a first-class quick-commerce requirement, and
forcing one category would require a disruptive schema change later.

### Store price and stock on variants now

Rejected. Pricing and inventory have separate lifecycle, concurrency, and
dark-store concerns. They will join to variants in later phases.

### Public catalog mutation endpoints

Rejected. Phase 2 provides customer authentication but not operator roles or
catalog approval controls. Exposing writes before those controls would create
an unsafe administrative surface.

## Trade-offs

- The many-to-many join adds one table and join work, but avoids product
  duplication and supports merchandising flexibility.
- Public reads use bounded offset pagination initially. Cursor pagination can be
  added after production catalog ordering and filtering patterns are measured.
- Alcohol classification is stored for catalog presentation only. Eligibility,
  age verification, jurisdiction rules, and delivery blocking remain separate
  compliance decisions.
- Slugs are globally unique and case-insensitive. Renaming/redirect history is
  deferred until catalog mutation workflows are designed.
