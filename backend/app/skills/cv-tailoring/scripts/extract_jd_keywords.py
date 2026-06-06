"""JD keyword extractor — deterministic, no LLM.

Callable interface: extract_jd_keywords(jd_text: str) -> list[str]

Extracts a deduplicated list of meaningful technical and domain keywords
from a job description using pattern-based heuristics.
"""
from __future__ import annotations

import re

# Common stop-words and filler phrases that are not meaningful keywords
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "as", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "this", "that", "these",
    "those", "i", "we", "you", "he", "she", "they", "it", "our", "your",
    "their", "its", "from", "by", "up", "about", "into", "through", "during",
    "including", "until", "against", "among", "throughout", "despite",
    "towards", "upon", "concerning", "of", "to", "in", "for", "on", "with",
    "at", "by", "from", "as", "is", "was", "are", "were", "be", "been",
    "not", "no", "nor", "so", "yet", "both", "either", "neither", "not",
    "only", "own", "same", "such", "than", "too", "very", "just", "because",
    "if", "while", "although", "though", "however", "therefore", "thus",
    "experience", "skills", "knowledge", "ability", "proven", "strong",
    "excellent", "good", "great", "high", "working", "work", "team",
    "role", "position", "candidate", "applicant", "required", "preferred",
    "ideally", "desirable", "essential", "must", "need", "needs",
    "responsibilities", "requirements", "qualifications", "duties",
    "opportunity", "join", "looking", "seeking", "want", "wanted",
    "will", "please", "apply", "send", "email", "contact", "us",
    "company", "organisation", "organization", "business", "employer",
})

# Known tech/domain terms that are always worth extracting (multi-word first)
_KNOWN_TECH = [
    "machine learning", "deep learning", "natural language processing",
    "computer vision", "data science", "data engineering", "data analysis",
    "software engineering", "systems architecture", "cloud architecture",
    "product management", "project management", "programme management",
    "agile delivery", "scrum master", "stakeholder management",
    "ci/cd", "devops", "mlops", "devsecops",
    "aws", "azure", "gcp", "google cloud",
    "kubernetes", "docker", "terraform", "ansible", "helm",
    "python", "java", "javascript", "typescript", "go", "rust", "c++",
    "react", "reactjs", "nodejs", "node.js", "fastapi", "django", "flask",
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "spark", "kafka", "airflow", "dbt", "snowflake", "databricks",
    "langchain", "openai", "llm", "rag", "vector database", "chromadb",
    "rest api", "graphql", "grpc", "microservices", "event-driven",
    "sql", "nosql", "etl", "elt", "data warehouse", "data lake",
    "agile", "scrum", "kanban", "safe", "itil", "prince2", "pmp",
    "ir35", "contract", "outside ir35",
]


def extract_jd_keywords(jd_text: str) -> list[str]:
    """Extract a deduplicated keyword list from a job description.

    Args:
        jd_text: Raw job description text.

    Returns:
        Sorted, deduplicated list of meaningful keywords (lowercase).
    """
    text_lower = jd_text.lower()
    found: set[str] = set()

    # 1. Multi-word tech terms (match first to avoid splitting)
    for term in _KNOWN_TECH:
        if term in text_lower:
            found.add(term)

    # 2. Single capitalised tokens that look like tech names (e.g. "Python", "AWS")
    tokens = re.findall(r"\b[A-Z][a-zA-Z0-9+#./]{1,20}\b", jd_text)
    for token in tokens:
        lower = token.lower()
        if lower not in _STOP_WORDS and len(lower) > 2:
            found.add(lower)

    # 3. Common abbreviations in all-caps (e.g. API, SQL, LLM)
    abbrevs = re.findall(r"\b[A-Z]{2,8}\b", jd_text)
    for abbrev in abbrevs:
        lower = abbrev.lower()
        if lower not in _STOP_WORDS:
            found.add(lower)

    return sorted(found)
