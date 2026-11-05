# Domain Docs

How engineering skills should consume this repo's domain documentation.

## Before exploring, read these

- `GLOSSARY.md` at the repo root, when present.
- `docs/adr/`: read ADRs that touch the area being changed.

If these files do not exist, proceed without flagging their absence. The domain-modeling workflow creates them when terms or decisions are resolved.

## File structure

```text
/
├── GLOSSARY.md
├── docs/adr/
│   └── 0001-example-decision.md
└── atlas/
```

## Use the glossary's vocabulary

Use domain terms as defined in `GLOSSARY.md`. If a needed concept is not defined, reconsider the terminology or note the gap for domain modeling.

## Flag ADR conflicts

If a proposed change contradicts an existing ADR, call out the ADR explicitly rather than silently overriding it.
