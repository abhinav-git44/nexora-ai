# RAG Design

## Pipeline
```
upload → validate (type, magic bytes, size, zip-bomb, macros, encoding) → store (org-prefixed key) → job: extract
→ sections (pages / headings / table rows) → chunk (strategy) → injection scoring → embed (versioned model)
→ store chunks (+ generated tsvector) → summary (fast route) → notify → fire "document_uploaded" workflows
query → hybrid retrieval (vector top-24 ∥ keyword top-24, both permission-filtered in SQL) → RRF fusion (k=60) → rerank
→ context assembly (≤ 6k tokens, neutralised, <document n=…> blocks) → grounded prompt → answer → citation verification
```

## Components
| Stage | Implementation | Configurable |
|---|---|---|
| Extraction | pypdf (per page), python-docx (headings + tables), openpyxl/csv (rows rendered as `col: value` lines, 25 rows/section), Markdown headings | OCR adapter (pytesseract + pdf2image) when installed |
| Chunking | `recursive` (paragraphs → sentences, ~350 tokens, 50 overlap) · `sentence` (~200) · `fixed` (300 chars×4) | per document, re-index to switch |
| Embeddings | `text-embedding-3-small` (1536-d) when OpenAI key present, else `local-hash-v1` (384-d signed feature hashing of unigrams+bigrams) | `EMBEDDING_PROVIDER` |
| Embedding versioning | `embedding_model` per chunk; dimension-less column; per-model HNSW expression index; retrieval filters to the active model → safe background re-embed | — |
| Vector search | cosine distance on cast vector (uses HNSW) | top-k candidates |
| Keyword search | `to_tsquery` OR of query keywords on generated `tsvector` (GIN) | — |
| Fusion | Reciprocal Rank Fusion, k = 60 | `RRF_K` |
| Reranking | 0.45·normalised RRF + 0.45·query-term coverage + phrase bonus + 0.1·vector − 0.3·injection risk | swappable with a cross-encoder |
| Filters | document ids, file types, tags, workspace | API + UI |
| Access control | `org_id` + `min_role` rank ≤ caller rank OR caller in `allowed_user_ids`, in SQL | per document |
| Citations | `[n]` markers mapped to chunk/doc/page/section; verification = lexical support of the cited sentence by the chunk (≥0.3) | threshold |

## Why hybrid
Business documents mix exact identifiers (policy numbers, amounts, SKUs) that vector search blurs with paraphrased questions that
keyword search misses. RRF needs no score calibration between the two retrievers.

## Chunking evaluation (measured)
`ai-engine/run_eval.py --chunking-sweep` on the 5-document golden corpus (local embeddings): recursive, sentence and fixed all scored
**hit@1 0.929 · hit@6 1.0 · MRR 0.964**. The corpus is too small and the documents too short to discriminate strategies — the result
says "no regression", not "strategies are equivalent". Recursive remains the default (keeps headings with their paragraphs); re-run
on design-partner corpora before changing defaults.

## Injection defence in RAG
Chunks are scored at index time (`injection_risk`), flagged counts surface in the UI, instruction-like spans are replaced with
`[filtered: instruction-like text removed]` before reaching any model, flagged chunks are down-ranked, and every prompt states that
`<document>` content is untrusted data. The golden set includes a contract with an embedded "ignore all previous instructions…"
line — injection resistance 1.0 in the current run.

## Known limitations
Lexical citation verification can mark a correct paraphrase as unverified (UI shows it as "verify against source", not as wrong);
local embeddings capture lexical similarity only; no table-aware chunking for very wide spreadsheets; OCR requires system packages.
