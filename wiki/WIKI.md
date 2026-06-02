# Wiki Schema

This is the schema for the Family Email Monitor project wiki.
It tells the LLM how to maintain, update, and extend the wiki.

## Structure

```
wiki/
  WIKI.md                  ← this file — schema and conventions
  index.md                 ← catalog of all pages (update on every change)
  log.md                   ← append-only chronological log
  overview.md              ← project goals, status, family use case
  architecture.md          ← full system design and data flow
  nanoclaw.md              ← NanoClaw platform concepts
  langchain-filter.md      ← Python LangChain pre-filter design
  email-classification.md  ← classification criteria and prompt design
  decisions.md             ← technology decisions and rationale
  sources/                 ← raw source documents (immutable, LLM reads only)
```

## Page Format

Each wiki page should begin with:

```markdown
# Page Title

> One-line summary of what this page covers.

**Last updated:** YYYY-MM-DD
**Related:** [[page-name]], [[page-name]]
```

Cross-references use `[[page-name]]` (Obsidian-style wikilinks).

## LLM Workflows

### Ingest a new source
1. Read the source document
2. Discuss key takeaways with the user
3. Write or update relevant wiki pages
4. Update `index.md` with any new pages
5. Append an entry to `log.md`

### Answer a query
1. Read `index.md` to find relevant pages
2. Read those pages
3. Synthesize an answer
4. If the answer is valuable, offer to file it as a new wiki page

### Lint the wiki
- Check for contradictions between pages
- Find orphan pages (no inbound links)
- Find concepts mentioned but lacking their own page
- Check for stale claims superseded by newer decisions

## Conventions

- Keep pages focused — one concept, decision, or system component per page
- File decisions in `decisions.md` with rationale and trade-offs noted
- Log every session in `log.md` with format: `## [YYYY-MM-DD] <type> | <title>`
- Never modify files in `sources/` — they are immutable raw inputs
- When a decision is reversed, update `decisions.md` and note the change in `log.md`
