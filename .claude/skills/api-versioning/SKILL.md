---
name: api-versioning
description: Reference for `/api/v1/` prefix discipline + the v1→v2 deprecation policy. Read when adding endpoints or contemplating a schema-breaking change.
when_to_use: Adding a new endpoint, designing a request/response schema change, or considering a v2 split.
user-invocable: false
---

# API Versioning — `/api/v1/` Prefix + Deprecation Policy

## Why we bake `/api/v1/` from day one

The day a schema-breaking change lands, you have two options: break every existing
client on Tuesday, or live alongside the old shape for a deprecation window. Without
a version prefix, only the first option exists. Baking `/api/v1/` from day one buys
the second option for free.

This is a once-a-decade investment for an early-life cost of `len("/v1")` bytes per
URL. Per the v0.6.0 plan, it's done.

## Active double-mount: `/api` (legacy) + `/api/v1` (current)

Every product generated from v0.6.0+ templates double-mounts the auth-protected
router:

```python
app.include_router(api_router, prefix=API_LEGACY_PREFIX)  # /api/<path>
app.include_router(api_router, prefix=API_V1_PREFIX)      # /api/v1/<path>
```

Every endpoint is reachable at **both** paths. This was a deliberate choice over
hard-flipping to /api/v1 only: customer products like `auth-demo-869` already call
existing services via the unversioned `/api/<foo>` path; a hard-flip would 404 them
on the next service amendment. Double-mount lets each service drop the legacy
prefix one-at-a-time when its callers have migrated.

**When to drop the legacy `/api` mount on a service:**

1. Confirm zero callers of the unversioned path. Cost-events / audit logs filtered
   to `/api/<foo>` (no `/v1`) over the last 30 days should be empty.
2. Open an amendment for that service. The amendment removes the legacy
   `app.include_router(..., prefix=API_LEGACY_PREFIX)` line.
3. Deploy. /api/v1 keeps working; /api/<foo> returns 404.

If callers still exist, EITHER migrate them first OR start the deprecation header
window (see policy below) and revisit at Day 365.

## What's in scope

- **Versioned**: every endpoint on `api_router` — reachable at both /api/<path>
  (legacy) and /api/v1/<path> (current).
- **Unversioned**: `/api/health` and similar operational endpoints. Registered
  directly on `app`. Never break — they exist for orchestration, not for client
  consumption.

When adding a new endpoint, register it on `api_router`, NOT on `app` directly.
The double-mount takes care of both legacy and v1 reachability.

## When v2 is needed

A v2 split is justified ONLY for **schema-breaking changes the existing field
catalog can't describe**. Examples:

- Auth-service migrating from RS256 JWT to OIDC discovery (token shape changes)
- Payment-service switching processor and the billing fields don't 1:1 map
- Cost-attribution moving from `cost_minor` to a structured Money type

Examples that are NOT v2:
- Adding a field — extend the existing v1 schema (additive-only invariant covers this).
- Renaming a field — bump the spec, deprecate the old name in v1.
- New endpoint — add to v1.
- Bug fix changing observed behaviour — not a contract change unless the bug was load-bearing.

If unsure, default to "stay on v1, extend additively". A v2 is expensive — both
sides live for ≥12 months.

## Deprecation policy

When v2 ships:

1. **Day 0 — v2 lands alongside v1.** Both versions are mounted on the app.
   `/api/v1/foo` and `/api/v2/foo` are both reachable; new clients use v2;
   existing clients keep working unchanged.

2. **Day 0 → Day 180 — silent overlap.** No deprecation header on v1. New
   client work happens against v2. Existing clients have no urgency.

3. **Day 180 — start the deprecation header.** Every v1 response gets:

   ```
   Deprecation: true
   Sunset: <ISO8601 date, ≥365 days from Day 0>
   Link: </api/v2/foo>; rel="successor-version"
   ```

   IETF RFC 8594 (Sunset) + RFC draft (Deprecation). Both ops crews and
   client libraries can detect these mechanically.

4. **Day 365 — v1 retires.** v1 routes return 410 Gone with a body explaining
   the migration path. Logs the request_id of any caller still hitting v1 so
   we can name them.

The minimum window is **365 days side-by-side**. Extend if a critical client
hasn't migrated. Shorter windows have to clear with the customer org —
documented exception, not the norm.

## The double-mount rule (when v2 lands)

When implementing v2, mount both routers on the same app:

```python
app.include_router(api_router_v1)  # /api/v1/foo (declared with prefix=/api/v1)
app.include_router(api_router_v2)  # /api/v2/foo (declared with prefix=/api/v2)
```

DO NOT subclass v2 from v1. Each version is its own independent router with
its own handlers, models, and tests. Shared code lives below the router layer
(domain logic, database, etc.). Subclassing tempts "just one more shared
method" until v1 and v2 are accidentally coupled — defeating the point of
the version split.

## What this skill is NOT

- Not a step-by-step v2 implementation guide. When v2 actually lands, write a
  feature plan with the specific schema changes; this skill is the meta-policy.
- Not a substitute for talking to clients. The 365-day window is the floor;
  the real timeline is set by who's still on v1 at Day 360.

## See Also

- `.claude/skills/microservices/SKILL.md` — service-to-service patterns
- `dreamteam-service-auth >= 0.6.0` — correlation primitives (request_id,
  end-user identity) auto-propagate through ServiceClient and middleware
- Memory: `feedback_schema_hook_coherence.md` — when versioning affects
  schemas, contract tests must anchor to the schema, not hand-coded shapes
