# Findings & Decisions

## Requirements
- Source: https://poetic-haupia-8d91dc.netlify.app/
- Destination: `/Users/lixiaofei05/Desktop/workspace/RAG企业知识库项目/RAG_PROJECT/test`
- Corrected requirement: each numbered top-level entry from 0 through 15 becomes one Markdown file.
- Every H3 child entry (for example 0.1 and 0.2) must remain inside its H2 parent file.
- The H1 project-title section is not an output file.
- Content must not be modified; only file and structure splitting is allowed.

## Research Findings
- Site loaded successfully; title is `CRM AI Agent 资深工程师面试档案（模拟）`.
- Left sidebar contains 52 clickable hash links.
- Main article contains exactly 52 corresponding sections/headings: one H1 root, sixteen H2 top-level steps (0 through 15), and thirty-five H3 substeps.
- Each heading is wrapped in a `section.level1`, `section.level2`, or `section.level3` with a stable ID matching the sidebar hash.
- Nested substeps are child sections of their top-level step, so direct children can be extracted without duplicating nested content.
- Article content uses a small, known HTML subset: headings, paragraphs, blockquotes, ordered/unordered lists, tables, fenced-code candidates, strong text, one horizontal rule, and one embedded SVG image.
- There are 15 tables, 6 preformatted code/text blocks, 3 blockquotes, and one inline `data:image/svg+xml;base64` image in step 6.4.
- Eleven top-level parent steps contain only their heading because all detailed content lives in their child steps; this is faithful to the page structure.
- Section 6.3 wraps a Python code block in `div.sourceCode`; section 6.4 stores the diagram inside a paragraph as an image.
- The converter successfully produced 52 Markdown files totaling 49,389 bytes.
- Files use a three-digit sidebar-order prefix and a sanitized source title; only the slash in `7.4 线上 A/B` required filename sanitization.
- A machine-readable extraction manifest records source section IDs, titles, heading levels, filenames, byte counts, and hashes.
- The root project-title section is genuinely the first item in the `Dossier index` list; all 52 entries are directory items.
- Final semantic verification stripped Markdown syntax and compared each file against its source section's visible text: 52 of 52 exact matches.
- Final mapping verification found 52 source sections, 52 manifest entries, 52 Markdown files, and zero missing/hash/mapping failures.
- Correction mapping contains 16 H2 parents, 35 H3 children, and one excluded H1 project-title section.
- The merge boundary is deterministic from `headingLevel`: each H2 starts a file and absorbs following H3 entries until the next H2.
- Temporary merged output contains exactly 16 Markdown files, 16 H2 headings, and all 35 H3 child headings.
- Each temporary file exactly equals its mapped source Markdown chunks joined only by a blank line; all content/hash/title checks passed.
- All 6 code blocks and the embedded SVG remain present after merging.
- Post-replacement validation passed: 16 root Markdown files, 16 H2 headings, 35 H3 headings, zero H1 headings, and zero content/hash failures.
- No standalone substep Markdown filename remains in the target directory.
- Final directory contains only the 16 numbered top-level Markdown outputs, totaling approximately 84 KB.
- Temporary merge and rollback directories were removed after successful validation.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Use ego-browser semantic/DOM extraction | Required browser skill and appropriate for exact structured extraction |
| Treat all 52 sidebar links as output units | Matches the literal left-side navigation, including substeps |
| Exclude child `section` elements from parent-step output | Maintains clean section boundaries and avoids duplicate content |
| Preserve original heading levels in each output file | Avoids altering document hierarchy during splitting |
| Preserve the embedded diagram in step 6.4 | The diagram is part of the source content and must not be dropped |
| Prefix filenames with `001` through `052` | Preserves the exact sidebar sequence in filesystem sorting |
| Merge each H2 file with all immediately following H3 files until the next H2 | Reconstructs the requested top-level section boundary without changing extracted content |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| `C.UTF-8` locale warning during plan initialization | Harmless on macOS; plan files were created successfully |
| Initial semantic verifier produced 16 false positives | Added heading and fenced-code state handling; corrected run passed 52/52 |

## Resources
- https://poetic-haupia-8d91dc.netlify.app/
