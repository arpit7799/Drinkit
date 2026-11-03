# ADR 0014: Party Mode, Collaborative Group Ordering, and Curated Party Packs

- Status: Accepted
- Date: 2026-11-03

## Context

Drinkit operates as a premium quick-commerce platform specializing in alcoholic and non-alcoholic beverages, mixers, ice, snacks, and recovery supplies. Unlike standard grocery platforms, social beverage consumption is inherently collaborative—multiple people gather at an apartment or venue and have distinct beverage preferences (e.g., Gin drinkers, Beer drinkers, sober/mocktail preferences). In traditional apps, one host must repeatedly collect individual drink orders over WhatsApp or phone calls, leading to order dropoffs, incorrect brands, and forgotten mixers or ice.

## Decision

Implement a dedicated Party Mode and Collaborative Group Ordering engine (`app.modules.party`):

1. **Party Room Sessions (`party_sessions`)**:
   - Host generates a room with an unambiguous 6-character room code (`invite_code`), destination address, and optional spending limit.
   - Friends join instantly (`party_participants`) with participant nicknames.

2. **Attributed Shared Cart (`party_cart_items`)**:
   - Items added to the group cart preserve who added them (`added_by_participant_id`), enabling participant-level accountability and bill transparency.
   - Host holds exclusive permission to lock the cart (`status = 'locked'`).

3. **Curated Bundles & Recovery Kits (`party_packs`, `party_pack_items`)**:
   - Merchandised 1-click bundles (e.g. Cocktail stations, Party Fiesta, Hangover Recovery) that inject multiple pre-selected SKUs directly into the group cart with a single action.

4. **Consolidated Checkout**:
   - On checkout, duplicate variant requests across all participants are consolidated into unified order lines, inventory is reserved atomically at the fulfillment dark store, taxes and promotions are computed, and a dark store picking task is dispatched.

## Consequences

- Creates an unmatched competitive differentiator for Drinkit in the quick-commerce landscape.
- Drives viral organic customer acquisition as guests who join a party room discover the Drinkit platform.
- Increases Average Order Value (AOV) by removing friction around purchasing complementary mixers, ice, and party snacks.
