# Party Mode, Collaborative Group Ordering & Curated Bundles

## Overview

Drinkit's signature **Party Mode** (`app.modules.party`) transforms beverage ordering from an isolated single-user experience into a collaborative social gathering. A party host launches a room with an unambiguous 6-character room code (`invite_code`), inviting guests to collectively add craft beers, spirits, mixers, snacks, and bagged ice into a shared live cart with 10-minute delivery execution.

---

## 1. Key Capabilities

### A. Collaborative Party Room
- **Host Room Creation**: The host specifies the delivery address, party name (e.g., "Friday Rooftop Gathering"), and an optional spending limit.
- **6-Character Invite Code**: Collision-free alphanumeric codes (e.g. `PRTY88`, excluding confusing glyphs like `0`, `O`, `1`, `I`) allow friends to join in seconds from mobile browsers without mandatory app downloads.
- **Participant Attribution**: Every item in the shared cart tracks `added_by_participant_id` and guest `nickname`, making it crystal clear who requested which drinks and snacks.

### B. Curated Party Packs & Recovery Bundles
Instead of browsing through dozens of catalog categories, hosts and guests can add pre-configured, discounted bundles directly to the party cart in 1 click:
- **Cocktail Stations**: e.g., *The Gin & Tonic Station* (Premium Gin, tonic water cans, limes, cocktail ice bag).
- **Party Fiesta Packs**: e.g., *Friday Night Beer & Chakhna Fiesta* (Craft beer packs, gourmet chips, roasted nuts, party cups).
- **Morning Recovery Kits**: e.g., *Sunday Morning Hangover Recovery Kit* (Electrolyte drinks, sparkling water, energy bars, recovery balms).

### C. Host Controls & Checkout
- **Cart Locking**: Host locks the room (`status = "locked"`) when ready to finalize order quantities.
- **Consolidation**: Identical SKUs added across multiple guests are automatically consolidated into single lines.
- **Order Checkout**: The host applies coupons or redeems Liver Points, converting the collaborative group cart into a confirmed order with inventory reservations and immediate dark-store picking task generation.

---

## 2. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/party/sessions` | Host creates a new party session |
| `GET` | `/api/v1/party/sessions/{id}` | Retrieve party session with members and shared cart |
| `GET` | `/api/v1/party/sessions/code/{code}` | Lookup party room by 6-character invite code |
| `POST` | `/api/v1/party/sessions/join` | Guest joins party session via invite code |
| `POST` | `/api/v1/party/sessions/{id}/items` | Add item to shared party cart |
| `PATCH` | `/api/v1/party/sessions/{id}/items/{item_id}` | Update quantity of an item in cart |
| `DELETE` | `/api/v1/party/sessions/{id}/items/{item_id}` | Remove item from party cart |
| `POST` | `/api/v1/party/sessions/{id}/add-pack` | 1-click add curated pack into party cart |
| `POST` | `/api/v1/party/sessions/{id}/lock` | Host locks cart before checkout |
| `POST` | `/api/v1/party/sessions/{id}/checkout` | Host converts collaborative cart into order |
| `GET` | `/api/v1/party/packs` | Browse curated party packs and recovery bundles |
| `POST` | `/api/v1/party/packs` | Create curated pack (merchandising) |
