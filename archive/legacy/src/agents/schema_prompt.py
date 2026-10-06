"""
Schema prompt extraction for the Northwind Agentic KG.

Authoritative contract: SCHEMA.md
Mechanical extraction: Parse SCHEMA.md markdown tables to generate
LLM schema prompt. Never hand-edited.

PURCHASED correction applied: Customer->Order edge type is PURCHASED (not ORDER).
This is the contract correction that a hand-maintained prompt would miss.

Extracts:
1. Node labels with key properties and name properties
2. Relationship types with direction (From → To)
3. Core traversal patterns as few-shot Cypher examples
4. Rules for the exploratory tool (run_readonly_cypher)
"""

import re
from typing import Optional
from pathlib import Path


# =============================================================================
# SCHEMA.md PATH
# =============================================================================

def _get_schema_path() -> Path:
    """Get the path to SCHEMA.md from the repo root."""
    # Navigate up from this file to repo root
    repo_root = Path(__file__).parent.parent.parent
    return repo_root / "SCHEMA.md"


# =============================================================================
# MARKDOWN TABLE PARSER
# =============================================================================

def _parse_markdown_table(table_text: str) -> list[dict]:
    """
    Parse a markdown table into a list of dictionaries.
    
    Example:
        | Header1 | Header2 |
        |---|---|
        | val1 | val2 |
    
    Returns: [{'Header1': 'val1', 'Header2': 'val2'}]
    """
    lines = table_text.strip().split('\n')
    
    # Skip empty lines
    lines = [line.strip() for line in lines if line.strip()]
    
    if len(lines) < 2:
        return []
    
    # Parse headers (first line)
    header_line = lines[0]
    headers = _parse_table_row(header_line)
    
    # Skip separator line (second line, contains ---)
    rows = []
    for line in lines[2:]:
        if '|' in line and '---' not in line:
            row = _parse_table_row(line)
            if len(row) == len(headers):
                rows.append(dict(zip(headers, row)))
    
    return rows


def _parse_table_row(line: str) -> list[str]:
    """Parse a single markdown table row."""
    # Remove leading/trailing pipes and whitespace
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    
    # Split by pipe and strip each cell
    cells = [cell.strip() for cell in line.split('|')]
    return cells


# =============================================================================
# EXTRACTION FUNCTIONS
# =============================================================================

def extract_labels(schema_text: str) -> list[dict]:
    """
    Extract node labels from SCHEMA.md.
    
    Returns list of dicts with:
    - label: The node label name
    - count: Number of nodes
    - key: Key property
    - name_property: Name property (or None if no name)
    - properties: List of properties
    """
    # Find the Node labels section
    labels_section = _extract_section(schema_text, "Node labels")
    if not labels_section:
        return []
    
    # Find the first table in the section (table starts with |)
    # Split by lines and find the first line starting with |
    lines = labels_section.split('\n')
    table_lines = []
    in_table = False
    skip_header = True  # Skip the header row (first | line)
    for line in lines:
        if line.strip().startswith('|') and not line.strip().startswith('|---'):
            if not in_table:
                in_table = True
                # Skip the header row
                if skip_header:
                    skip_header = False
                    continue
            table_lines.append(line)
        elif in_table and line.strip() == '':
            break
    
    if not table_lines:
        return []
    
    # Parse the table from the collected lines
    # Prepend header and separator for _parse_markdown_table
    table_text = f"| Label | Count | Key | Name property | Properties (verified, types) |\n|---|---|---|---|---|\n"
    table_text += '\n'.join(table_lines)
    rows = _parse_markdown_table(table_text)
    
    labels = []
    for row in rows:
        label = row.get('Label', '')
        if not label:
            continue
        
        labels.append({
            'label': label,
            'count': row.get('Count', '0'),
            'key': row.get('Key', ''),
            'name_property': row.get('Name property', None),
            'properties': _parse_properties(row.get('Properties (verified, types)', '')),
        })
    
    return labels


def extract_relationships(schema_text: str) -> list[dict]:
    """
    Extract relationship types from SCHEMA.md.
    
    Returns list of dicts with:
    - type: Relationship type name
    - from_label: Source label
    - to_label: Target label  
    - count: Number of relationships
    - properties: List of relationship properties
    - meaning: Human-readable meaning
    """
    # Find the Relationships section
    rels_section = _extract_section(schema_text, "Relationships")
    if not rels_section:
        return []
    
    # Parse the table
    rows = _parse_markdown_table(rels_section)
    
    relationships = []
    for row in rows:
        rel_type = row.get('Type', '')
        if not rel_type:
            continue
        
        # Parse "From → To" format
        direction = row.get('From → To', '')
        from_to = _parse_direction(direction)
        
        relationships.append({
            'type': rel_type,
            'from_label': from_to[0] if from_to else '',
            'to_label': from_to[1] if from_to else '',
            'count': row.get('Count', '0'),
            'properties': _parse_properties(row.get('Properties (verify)', '')),
            'meaning': row.get('Meaning', ''),
        })
    
    return relationships


def extract_traversal_patterns(schema_text: str) -> list[dict]:
    """
    Extract core traversal patterns from SCHEMA.md.
    
    Returns list of dicts with:
    - name: Pattern name
    - description: Human-readable description
    - cypher: Cypher example
    """
    # Find the Core traversal patterns section
    patterns_section = _extract_section(schema_text, "Core traversal patterns")
    if not patterns_section:
        # Try with full heading
        patterns_section = _extract_section(schema_text, "Core traversal patterns (the demo beats as Cypher shapes)")
    if not patterns_section:
        return []
    
    # Extract code blocks (Cypher) and their preceding text
    patterns = []
    
    # Split by code blocks
    cypher_blocks = re.findall(r'```cypher\s*\n(.*?)```', patterns_section, re.DOTALL)
    
    # Also extract the pattern names and descriptions
    # Pattern: **Pattern Name:** followed by description, then code block
    pattern_matches = re.finditer(
        r'\*\*(.*?)\*\*:\s*(.*?)(?=\n\n|\n\*\*|\n```|$)',
        patterns_section,
        re.DOTALL
    )
    
    for i, match in enumerate(pattern_matches):
        name = match.group(1).strip()
        description = match.group(2).strip()
        cypher = cypher_blocks[i] if i < len(cypher_blocks) else ''
        
        patterns.append({
            'name': name,
            'description': description,
            'cypher': cypher.strip(),
        })
    
    return patterns


def extract_rules(schema_text: str) -> list[str]:
    """
    Extract rules for the exploratory tool from SCHEMA.md.
    
    Returns list of rule strings.
    """
    # Find the Rules section
    rules_section = _extract_section(schema_text, "Rules for the exploratory tool")
    if not rules_section:
        return []
    
    # Extract bullet points
    rules = re.findall(r'^- (.*)$', rules_section, re.MULTILINE)
    return rules


def extract_revenue_rule(schema_text: str) -> Optional[str]:
    """
    Extract the revenue rule from SCHEMA.md.
    
    Returns the revenue rule string or None.
    """
    # Look for the revenue rule in structural facts or core traversal patterns
    pattern = r'Revenue must be computed as `([^`]+)`'
    match = re.search(pattern, schema_text)
    if match:
        return match.group(1)
    return None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _extract_section(text: str, section_name: str) -> Optional[str]:
    """Extract a section from the schema text by its heading."""
    # Escape special regex characters in section_name
    escaped = re.escape(section_name)
    # Try to find the section heading (allow any characters between ## and newline)
    pattern = rf'##\s+{escaped}.*?\s*\n(.*?)(?=\n\n##|\n\n###|$)'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    return None


def _parse_direction(direction: str) -> tuple[str, str]:
    """
    Parse a direction string like "Customer → Order" into (from, to).
    """
    direction = direction.strip()
    if '→' in direction:
        parts = direction.split('→', 1)
        return (parts[0].strip(), parts[1].strip())
    elif '->' in direction:
        parts = direction.split('->', 1)
        return (parts[0].strip(), parts[1].strip())
    return ('', '')


def _parse_properties(prop_string: str) -> list[str]:
    """
    Parse a properties string like "unitPrice (Double), unitsInStock (Long)" 
    into a list of property names.
    """
    if not prop_string:
        return []
    
    # Remove parentheses and split by commas
    props = []
    # Match: propertyName (Type) or just propertyName
    matches = re.findall(r'([^,(]+)', prop_string)
    for match in matches:
        prop = match.strip()
        if prop:
            props.append(prop)
    
    return props


# =============================================================================
# MAIN FUNCTION: Generate Schema Prompt
# =============================================================================

def generate_schema_prompt() -> str:
    """
    Generate the complete schema prompt for the exploratory tool's LLM.
    
    This is the mechanical extraction from SCHEMA.md — never hand-edited.
    The prompt includes:
    1. Instance summary
    2. Node labels with keys and properties
    3. Relationship types with direction
    4. Structural facts
    5. Core traversal patterns
    6. Revenue rule
    7. Rules for the exploratory tool
    
    Returns: Complete schema prompt string
    """
    schema_path = _get_schema_path()
    
    if not schema_path.exists():
        raise FileNotFoundError(
            f"SCHEMA.md not found at {schema_path.absolute()}. "
            "This file is required to generate the schema prompt."
        )
    
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_text = f.read()
    
    # Extract all components
    labels = extract_labels(schema_text)
    relationships = extract_relationships(schema_text)
    patterns = extract_traversal_patterns(schema_text)
    rules = extract_rules(schema_text)
    revenue_rule = extract_revenue_rule(schema_text)
    
    # Build the prompt
    prompt_parts = []
    
    # Header
    prompt_parts.append("# Neo4j Schema for Northwind Knowledge Graph")
    prompt_parts.append("")
    prompt_parts.append("You are an expert Cypher query generator for a Neo4j knowledge graph.")
    prompt_parts.append("The following schema is the COMPLETE and AUTHORITATIVE universe of the graph.")
    prompt_parts.append("Use ONLY the labels, relationship types, and properties described below.")
    prompt_parts.append("")
    
    # Instance summary
    prompt_parts.append("## Instance Summary")
    prompt_parts.append("")
    
    # Extract instance summary table
    summary_section = _extract_section(schema_text, "Instance summary")
    if summary_section:
        prompt_parts.append(summary_section)
        prompt_parts.append("")
    
    # Node Labels
    prompt_parts.append("## Node Labels")
    prompt_parts.append("")
    prompt_parts.append("**Naming convention:** There is NO generic 'name' property. Use the exact name property for each label.")
    prompt_parts.append("")
    
    for label in labels:
        prompt_parts.append(f"- **{label['label']}**")
        prompt_parts.append(f"  - Key property: `{label['key']}`")
        if label['name_property'] and label['name_property'] != '—':
            prompt_parts.append(f"  - Name property: `{label['name_property']}`")
        if label['properties']:
            props_str = ', '.join(label['properties'][:10])  # Limit to first 10
            if len(label['properties']) > 10:
                props_str += ', ...'
            prompt_parts.append(f"  - Properties: {props_str}")
        prompt_parts.append("")
    
    # Relationships
    prompt_parts.append("## Relationship Types")
    prompt_parts.append("")
    
    for rel in relationships:
        dir_str = f"{rel['from_label']} → {rel['to_label']}"
        prompt_parts.append(f"- **{rel['type']}**: {dir_str}")
        if rel['properties']:
            props_str = ', '.join(rel['properties'])
            prompt_parts.append(f"  - Properties: {props_str}")
        if rel['meaning']:
            prompt_parts.append(f"  - Meaning: {rel['meaning']}")
        prompt_parts.append("")
    
    # Structural Facts
    prompt_parts.append("## Structural Facts")
    prompt_parts.append("")
    struct_section = _extract_section(schema_text, "Structural facts")
    if struct_section:
        # Clean up the section text
        struct_text = struct_section.strip()
        prompt_parts.append(struct_text)
        prompt_parts.append("")
    
    # Revenue Rule (explicitly call out)
    if revenue_rule:
        prompt_parts.append("## Revenue Rule")
        prompt_parts.append("")
        prompt_parts.append(f"**CRITICAL:** Revenue MUST be computed as: `{revenue_rule}`")
        prompt_parts.append("")
        prompt_parts.append("This is MANDATORY. ORDERS edge properties (quantity, unitPrice, discount) exist on only ~5% of edges.")
        prompt_parts.append("Always use coalesce(line.unitPrice, p.unitPrice) to fall back to Product.unitPrice.")
        prompt_parts.append("Treat null quantity as an unusable line and count it separately.")
        prompt_parts.append("")
    
    # Core Traversal Patterns
    prompt_parts.append("## Core Traversal Patterns (Few-shot Examples)")
    prompt_parts.append("")
    prompt_parts.append("Use these as templates for generating Cypher queries.")
    prompt_parts.append("")
    
    for pattern in patterns:
        prompt_parts.append(f"### {pattern['name']}")
        prompt_parts.append("")
        prompt_parts.append(pattern['description'])
        prompt_parts.append("")
        prompt_parts.append("```cypher")
        prompt_parts.append(pattern['cypher'])
        prompt_parts.append("```")
        prompt_parts.append("")
    
    # Rules for Exploratory Tool
    prompt_parts.append("## Rules for Cypher Generation")
    prompt_parts.append("")
    prompt_parts.append("Follow these rules STRICTLY when generating queries:")
    prompt_parts.append("")
    
    for i, rule in enumerate(rules, 1):
        prompt_parts.append(f"{i}. {rule}")
    
    prompt_parts.append("")
    prompt_parts.append("REMEMBER: You must use ONLY the schema elements defined above. Do not invent labels, relationships, or properties.")
    
    return '\n'.join(prompt_parts)


# =============================================================================
# UTILITY: Get Schema Components (for tool registration, etc.)
# =============================================================================

def get_labels() -> list[dict]:
    """Get node labels from SCHEMA.md."""
    schema_path = _get_schema_path()
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_text = f.read()
    return extract_labels(schema_text)


def get_relationships() -> list[dict]:
    """Get relationship types from SCHEMA.md."""
    schema_path = _get_schema_path()
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_text = f.read()
    return extract_relationships(schema_text)


def get_traversal_patterns() -> list[dict]:
    """Get core traversal patterns from SCHEMA.md."""
    schema_path = _get_schema_path()
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_text = f.read()
    return extract_traversal_patterns(schema_text)


def get_revenue_rule() -> Optional[str]:
    """Get the revenue rule from SCHEMA.md."""
    schema_path = _get_schema_path()
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_text = f.read()
    return extract_revenue_rule(schema_text)


# Clear cache for testing
def clear_schema_prompt_cache() -> None:
    """Clear the schema prompt cache (for testing)."""
    global _schema_prompt_cache
    _schema_prompt_cache = None
