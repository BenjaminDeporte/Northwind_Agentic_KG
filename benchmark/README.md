# Northwind Benchmark

`northwind_questions.csv` is the canonical 20-question evaluation set for the redesigned architectures.

Columns:

- `Group`: question category;
- `Question`: user question;
- `Answer`: ground-truth answer used for evaluation;
- `Comment`: informational provenance, including the Cypher used to establish the ground truth.

The Cypher in `Comment` is reference metadata. It is not submitted as the expected answer and is not used as a generated-query score.
