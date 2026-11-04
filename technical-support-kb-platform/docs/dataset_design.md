# Synthetic dataset design

## Composition

The seed contains **10 users**, **40 knowledge-base items**, and **160
interactions**. Every person, support case, and source URL is fictional. The
source URLs use `docs.example.invalid` and are deliberately unreachable.

The 40 resources are evenly divided among Networking, Operating Systems,
Database Systems, Deployment and DevOps, and Security (eight each). They
include troubleshooting guides, FAQs, configuration manuals, and release
notes. Each entry has a distinct technical symptom or task, diagnostic checks,
and a concrete resolution or verification step. Source type, URI, and section
are embedded in each item. Version-specific pairs include Ubuntu 22.04/24.04
resolver guides, PostgreSQL 15/16 SCRAM guides, and Kubernetes 1.28/1.29
CrashLoopBackOff guides. These provide controlled near matches for later
retrieval experiments.

The users are fictional support engineers with different two-product
preferences. The `password_hash` field holds a `disabled:sha256:` marker and
a deterministic digest of a non-login seed string. There is no plaintext
password or usable login credential for these accounts; they cannot log in.

## Generation and reproducibility

Run `python -m scripts.seed_data` after `python -m scripts.init_db`. The
generator uses a fixed resource catalog, a fixed random seed (`603`), fixed
UTC dates, and ObjectIds derived from SHA-256 of the seed namespace,
collection name, and stable record key. The default namespace is
`assignment6-synthetic-v1`. Thus the same code and namespace produce the same
records and references on every run.

The seed stores `seed_namespace` as an extra provenance field. Before writing,
it rejects any generated `_id` already held by a document with another
namespace. It uses `$setOnInsert` upserts, so existing records are never
updated; it neither drops collections nor deletes data. A conflicting unique
email from an unrelated document would stop seeding without overwriting it.
The script refuses databases whose names end in `_test`, protecting the
integration-test databases from accidental command-line seeding.

## Interaction pattern

Each engineer has eight two-event sessions: one `view` followed five minutes
later by `selection`, `helpful`, `unhelpful`, or `rating` on the same item.
Across the dataset there are 80 views, 30 selections, 20 helpful votes, 10
unhelpful votes, and 20 ratings. Ratings are integers from 1 to 5 and occur
only on rating events. The first 40 sessions ensure every resource is viewed.
Later sessions use weighted sampling: early catalog entries are more popular,
preferred products are more likely for each user, and lower-quality cases are
more likely to receive unhelpful feedback. This creates variation without
pretending to model real support behavior. All interactions reference the
generated user and knowledge item ObjectIds.

## Limits

The corpus is small, authored for coursework, and does not reproduce real
incident frequencies, human language variation, privacy constraints, or
production feedback bias. The usefulness weights and timestamps are synthetic.
Results from later search or recommendation experiments should not be treated
as evidence of real-world effectiveness without evaluation on suitable data.
