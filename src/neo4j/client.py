"""Read-only Neo4j access for the Northwind knowledge graph."""
import os
import re
from typing import Any, Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase, READ_ACCESS, ResultSummary

load_dotenv()


class Neo4jClient:
    _instance: Optional["Neo4jClient"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_driver") and self._driver is not None:
            return
        uri = os.getenv("NEO4J_URI")
        password = os.getenv("NEO4J_PASSWORD")
        if not uri or not password:
            raise ValueError("NEO4J_URI and NEO4J_PASSWORD must be set in .env")
        user = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER", "neo4j")
        self._database = os.getenv("NEO4J_DATABASE") or None
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    @staticmethod
    def _mask_literals_and_comments(query: str) -> str:
        """Blank quoted text and comments so clause checks see Cypher syntax only."""
        out = []
        i = 0
        state = "code"
        while i < len(query):
            char = query[i]
            nxt = query[i + 1] if i + 1 < len(query) else ""
            if state == "code":
                if char in ("'", '"', '`'):
                    state = char
                    out.append(" ")
                elif char == "/" and nxt == "/":
                    state = "line"
                    out.extend("  ")
                    i += 1
                elif char == "/" and nxt == "*":
                    state = "block"
                    out.extend("  ")
                    i += 1
                else:
                    out.append(char)
            elif state == "line":
                if char == "\n":
                    state = "code"
                    out.append("\n")
                else:
                    out.append(" ")
            elif state == "block":
                if char == "*" and nxt == "/":
                    state = "code"
                    out.extend("  ")
                    i += 1
                else:
                    out.append(" ")
            else:
                if char == "\\" and nxt:
                    out.extend("  ")
                    i += 1
                elif char == state:
                    if nxt == state and state in ("'", '"', '`'):
                        out.extend("  ")
                        i += 1
                    else:
                        state = "code"
                        out.append(" ")
                else:
                    out.append(" ")
            i += 1
        if state not in ("code", "line"):
            raise ValueError("Unterminated Cypher string or comment")
        return "".join(out)

    @classmethod
    def _normalize_read_only_query(cls, query: str) -> Optional[str]:
        """Remove one optional terminal statement delimiter; reject embedded delimiters."""
        if not isinstance(query, str) or not query.strip():
            return None
        try:
            code = cls._mask_literals_and_comments(query)
        except ValueError:
            return None
        semicolons = [index for index, char in enumerate(code) if char == ";"]
        if not semicolons:
            return query
        if len(semicolons) != 1:
            return None
        delimiter = semicolons[0]
        if code[delimiter + 1:].strip():
            return None
        return (query[:delimiter] + query[delimiter + 1:]).rstrip()

    def _validate_read_only(self, query: str) -> bool:
        normalized = self._normalize_read_only_query(query)
        if normalized is None:
            return False
        try:
            code = self._mask_literals_and_comments(normalized)
        except ValueError:
            return False
        if ";" in code:
            return False
        words = re.findall(r"[A-Za-z_][A-Za-z_0-9]*", code.upper())
        if not words or words[0] not in {"MATCH", "OPTIONAL", "WITH", "UNWIND", "RETURN"}:
            return False
        if words[0] == "OPTIONAL" and (len(words) < 2 or words[1] != "MATCH"):
            return False
        prohibited = {
            "CREATE", "MERGE", "DELETE", "DETACH", "SET", "REMOVE", "FOREACH",
            "CALL", "LOAD", "USE", "SHOW", "DROP", "ALTER", "GRANT", "DENY",
            "REVOKE", "START", "STOP", "PROFILE", "EXPLAIN",
        }
        return not any(word in prohibited for word in words)

    def _session(self):
        return self._driver.session(database=self._database, default_access_mode=READ_ACCESS)

    def run_read_query(self, query: str, parameters: dict[str, Any] | None = None) -> tuple[list[dict], ResultSummary]:
        normalized = self._normalize_read_only_query(query)
        if normalized is None or not self._validate_read_only(normalized):
            raise ValueError("Only one read-only Cypher statement is allowed")
        with self._session() as session:
            result = session.run(normalized, parameters or {})
            records = [dict(record) for record in result]
            return records, result.consume()

    def explain(self, query: str) -> bool:
        normalized = self._normalize_read_only_query(query)
        if normalized is None or not self._validate_read_only(normalized):
            raise ValueError("Only one read-only Cypher statement is allowed")
        with self._session() as session:
            session.run("EXPLAIN " + normalized).consume()
        return True


client = Neo4jClient()
