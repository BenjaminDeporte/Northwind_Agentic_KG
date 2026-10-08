"""Small benchmark-driven curated query registry for Architectures 3 and 4."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CuratedQuery:
    name: str
    description: str
    query: str


class CuratedQueryRegistry:
    def __init__(self, queries: list[CuratedQuery]):
        self._queries = {item.name: item for item in queries}

    @classmethod
    def default(cls) -> "CuratedQueryRegistry":
        return cls([
            CuratedQuery("count_customers", "Count all Customer nodes", "MATCH (c:Customer) RETURN count(c) AS customerCount"),
            CuratedQuery("count_orders", "Count all Order nodes", "MATCH (o:Order) RETURN count(o) AS orderCount"),
            CuratedQuery("count_products", "Count all Product nodes", "MATCH (p:Product) RETURN count(p) AS productCount"),
            CuratedQuery("count_alfki_orders", "Count orders placed by customer ALFKI", "MATCH (c:Customer {customerID: 'ALFKI'})-[:PURCHASED]->(o:Order) RETURN count(o) AS orderCount"),
            CuratedQuery("top_employee", "Find the employee who handled the most orders", "MATCH (e:Employee)-[:SOLD]->(o:Order) RETURN e.firstName + ' ' + e.lastName AS employeeName, count(o) AS orderCount ORDER BY orderCount DESC LIMIT 1"),
        ])

    def descriptions(self) -> list[dict[str, str]]:
        return [{"name": item.name, "description": item.description} for item in self._queries.values()]

    def query(self, name: str) -> str:
        try:
            return self._queries[name].query
        except KeyError as exc:
            raise ValueError(f"Unknown curated query: {name}") from exc


__all__ = ["CuratedQuery", "CuratedQueryRegistry"]
