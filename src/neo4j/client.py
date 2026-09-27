"""
Neo4j AuraDB Driver for Northwind Agentic KG.

Read-only enforcement: Driver level rejects any non-READ Cypher.
APOC is banned: Use plain Cypher only (no CALL apoc.meta.*).
"""

import os
from typing import Any, Optional

from neo4j import GraphDatabase, ResultSummary
from neo4j.exceptions import Neo4jError
from dotenv import load_dotenv

load_dotenv()


class Neo4jClient:
    """
    Read-only Neo4j driver for the Northwind knowledge graph.
    
    Invariant: No CREATE/MERGE/DELETE/SET/CALL statements permitted.
    """
    
    _instance: Optional["Neo4jClient"] = None
    
    def __new__(cls) -> "Neo4jClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if not hasattr(self, "_driver"):
            uri = os.getenv("NEO4J_URI")
            user = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD")
            database = os.getenv("NEO4J_DATABASE")
            
            if not uri or not password:
                raise ValueError(
                    "NEO4J_URI and NEO4J_PASSWORD must be set in .env"
                )
            
            self._driver = GraphDatabase.driver(
                uri, 
                auth=(user, password),
                database=database if database else None
            )
    
    def close(self) -> None:
        """Close the driver."""
        if hasattr(self, "_driver") and self._driver is not None:
            self._driver.close()
            self._driver = None
    
    def _validate_read_only(self, query: str) -> bool:
        """
        Validate that the query is read-only.
        
        Rejects: CREATE, MERGE, DELETE, SET, REMOVE, FOREACH, CALL {apoc.*}
        """
        query_upper = query.upper()
        
        # Ban write clauses
        write_clauses = ["CREATE", "MERGE", "DELETE", "DETACH DELETE", "SET", "REMOVE", "FOREACH"]
        for clause in write_clauses:
            if clause in query_upper:
                return False
        
        # Ban APOC calls
        if "CALL APOC" in query_upper or "CALL apoc" in query:
            return False
        
        return True
    
    def run_read_query(self, query: str, parameters: dict[str, Any] = None) -> tuple[list[dict], ResultSummary]:
        """
        Execute a read-only Cypher query.
        
        Args:
            query: The Cypher query string
            parameters: Optional query parameters
            
        Returns:
            Tuple of (list of result dicts, ResultSummary)
            
        Raises:
            ValueError: If query is not read-only
            Neo4jError: On execution failure
        """
        if not self._validate_read_only(query):
            raise ValueError(
                f"Read-only violation: Query contains write operations or APOC calls. Query: {query[:100]}..."
            )
        
        with self._driver.session() as session:
            result = session.run(query, parameters or {})
            records = [dict(record) for record in result]
            summary = result.consume()
            return records, summary
    
    def explain(self, query: str) -> bool:
        """
        Validate query via EXPLAIN (does not execute).
        
        Args:
            query: The Cypher query string
            
        Returns:
            True if valid, False otherwise
        """
        try:
            explain_query = f"EXPLAIN {query}"
            if not self._validate_read_only(explain_query):
                return False
            with self._driver.session() as session:
                session.run(explain_query)
                return True
        except Neo4jError:
            return False


# Singleton access
client = Neo4jClient()
