# Lexical search analysis

Generated: 2026-11-03T20:41:32.942631+00:00  
Database: `tech_support_recommender`  
Active catalog documents: 40

Results use the same `search_items` service as `GET /items/search`, with
MongoDB `catalog_text` scores and the API's deterministic tie-break order.
Scores are MongoDB text scores for each query and are not relevance judgments.

## PostgreSQL authentication

Matches: 5; returned: 5.  
Categories: Database Systems, Deployment and DevOps.  
Products: Kubernetes, PostgreSQL.

| Rank | Document ID | Title | Category | Product | Text score |
| ---: | --- | --- | --- | --- | ---: |
| 1 | `3378bfbd7e0afe0984d514ac` | PostgreSQL 16 SCRAM authentication mismatch | Database Systems | PostgreSQL | 4.940625 |
| 2 | `b3fa561ab8979e8484832841` | PostgreSQL 15 SCRAM authentication mismatch | Database Systems | PostgreSQL | 4.379167 |
| 3 | `d2df25d1fc2912b97ddd34ce` | Read a PostgreSQL EXPLAIN plan | Database Systems | PostgreSQL | 1.725000 |
| 4 | `98f4a52a31cf866117f19feb` | Investigate PostgreSQL table bloat | Database Systems | PostgreSQL | 1.725000 |
| 5 | `5a162230b7f1e4d5b129a35d` | Resolve ImagePullBackOff for private registry | Deployment and DevOps | Kubernetes | 0.571429 |

## VPN troubleshooting

Matches: 5; returned: 5.  
Categories: Networking, Operating Systems, Security.  
Products: RouterOS, Ubuntu, Vault, macOS.

| Rank | Document ID | Title | Category | Product | Text score |
| ---: | --- | --- | --- | --- | ---: |
| 1 | `2528cfbcc528fdcdb8410f4f` | Diagnose VPN packet fragmentation | Networking | RouterOS | 1.725000 |
| 2 | `d1eeca28dddc7e1a81a61a63` | Vault policy path troubleshooting | Security | Vault | 0.625000 |
| 3 | `82263432b87a0c319d5dee89` | Ubuntu 24.04 resolver stub troubleshooting | Operating Systems | Ubuntu | 0.583333 |
| 4 | `1b22ec20ad3d1c8b4da70aee` | Ubuntu 22.04 resolver stub troubleshooting | Operating Systems | Ubuntu | 0.583333 |
| 5 | `66685f3a830257dd8eebb202` | macOS 14 network extension change notes | Operating Systems | macOS | 0.516667 |

## Linux permissions

Matches: 4; returned: 4.  
Categories: Deployment and DevOps, Networking, Operating Systems, Security.  
Products: GitHub Actions, Nginx, Vault, systemd.

| Rank | Document ID | Title | Category | Product | Text score |
| ---: | --- | --- | --- | --- | ---: |
| 1 | `31ebc4f749d971bb9e7a138e` | GitHub Actions token permission change notes | Deployment and DevOps | GitHub Actions | 2.964762 |
| 2 | `4f973ae2d63021b399387fa2` | Load systemd service credentials from files | Operating Systems | systemd | 0.519231 |
| 3 | `fad29c27bc58c40923b244d4` | Nginx returns 502 Bad Gateway | Networking | Nginx | 0.516129 |
| 4 | `d1eeca28dddc7e1a81a61a63` | Vault policy path troubleshooting | Security | Vault | 0.514706 |

## Observed limitations

The query result lists show which categories and products share the queried
terms. Broad keyword matches can span different technical contexts. In particular,
words such as `authentication`, `troubleshooting`, and `permissions` may
describe different failure modes or products. MongoDB text search matches lexical
terms; it does not establish that a document resolves a user's specific issue.
The synthetic catalog has no independent relevance labels, so this report does
not calculate Recall@k, MRR, or nDCG@k or classify matches as relevant or irrelevant.
Ranking and score comparisons are meaningful only within the same query and
index configuration.
