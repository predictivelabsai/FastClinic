"""
Topic Analysis Utilities
========================

LLM-based topic extraction and classification for conversation messages using LangChain + OpenAI.
"""

import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

# Load environment variables
load_dotenv()


# Default topic categories for medical travel domain
DEFAULT_TOPICS = [
    "Treatment Inquiry",
    "Hospital Information",
    "Pricing & Costs",
    "Travel & Logistics",
    "Booking Process",
    "Medical Conditions",
    "Post-Operative Care",
    "Insurance & Payment",
    "Location & Destination",
    "General Questions",
    "Complaints & Issues",
    "Follow-up & Support",
]


@dataclass
class TopicResult:
    """Result of topic extraction for a single text."""
    text_id: Any
    primary_topic: str
    secondary_topics: List[str] = field(default_factory=list)
    confidence: float = 0.5
    keywords: List[str] = field(default_factory=list)
    raw_response: str = ""


@dataclass
class BatchTopicResult:
    """Result of batch topic extraction."""
    results: List[TopicResult]
    errors: List[Dict[str, Any]]


@dataclass
class TopicSummary:
    """Summary of topics across all analyzed texts."""
    topic_counts: Dict[str, int]
    topic_examples: Dict[str, List[str]]  # topic -> sample texts
    total_analyzed: int


def get_llm(model: str = "gpt-4o-mini", temperature: float = 0.1) -> ChatOpenAI:
    """
    Get a configured ChatOpenAI instance.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables")
    return ChatOpenAI(model=model, temperature=temperature, api_key=api_key)


def extract_topics_single(
    llm: ChatOpenAI,
    text: str,
    text_id: Any = None,
    allowed_topics: Optional[List[str]] = None,
) -> TopicResult:
    """
    Extract topics from a single text using LLM.
    
    Args:
        llm: Configured ChatOpenAI instance
        text: Text to analyze
        text_id: Optional identifier for the text
        allowed_topics: Optional list of allowed topic labels
    
    Returns:
        TopicResult with extracted topics
    """
    topics = allowed_topics or DEFAULT_TOPICS
    topics_list = "\n".join(f"- {t}" for t in topics)
    
    system_prompt = f"""You are a topic classification expert for a medical travel company. 
Classify the given text into topics from this list:

{topics_list}

Respond in this exact JSON format (no markdown, just raw JSON):
{{
    "primary_topic": "Most relevant topic from the list",
    "secondary_topics": ["Other relevant topics if any"],
    "confidence": 0.0-1.0,
    "keywords": ["key", "words", "from", "text"]
}}

Rules:
- primary_topic MUST be from the provided list
- secondary_topics should only include topics that are clearly relevant
- keywords should be 3-5 important words/phrases from the text
- confidence reflects how clearly the text fits the primary topic
"""

    user_prompt = f"Classify this text:\n\n{text[:2000]}"

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        raw = (response.content or "").strip()
        
        # Parse JSON
        import json
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        
        data = json.loads(raw)
        primary = data.get("primary_topic", "General Questions")
        
        # Validate primary topic is in allowed list
        if primary not in topics:
            # Find closest match or default
            primary_lower = primary.lower()
            for t in topics:
                if t.lower() in primary_lower or primary_lower in t.lower():
                    primary = t
                    break
            else:
                primary = "General Questions"
        
        return TopicResult(
            text_id=text_id,
            primary_topic=primary,
            secondary_topics=data.get("secondary_topics", []),
            confidence=float(data.get("confidence", 0.5)),
            keywords=data.get("keywords", []),
            raw_response=raw,
        )
    except Exception as e:
        return TopicResult(
            text_id=text_id,
            primary_topic="General Questions",
            confidence=0.0,
            raw_response=f"Error: {str(e)}",
        )


def extract_topics_batch(
    llm: ChatOpenAI,
    texts: List[Dict[str, Any]],
    text_key: str = "content",
    id_key: str = "id",
    allowed_topics: Optional[List[str]] = None,
    max_chars_per_text: int = 400,
) -> BatchTopicResult:
    """
    Extract topics from multiple texts in a single LLM call.
    
    Args:
        llm: Configured ChatOpenAI instance
        texts: List of dicts containing text and id
        text_key: Key for text content in each dict
        id_key: Key for text id in each dict
        allowed_topics: Optional list of allowed topic labels
        max_chars_per_text: Max characters per text
    
    Returns:
        BatchTopicResult with all results
    """
    if not texts:
        return BatchTopicResult(results=[], errors=[])
    
    topics = allowed_topics or DEFAULT_TOPICS
    topics_list = "\n".join(f"- {t}" for t in topics)
    
    # Prepare numbered list
    numbered_texts = []
    for i, item in enumerate(texts):
        text = (item.get(text_key) or "")[:max_chars_per_text]
        numbered_texts.append(f"[{i}] {text}")
    
    combined = "\n\n".join(numbered_texts)
    
    system_prompt = f"""You are a topic classification expert for a medical travel company.
Classify each numbered text into topics from this list:

{topics_list}

Respond in this exact JSON format (no markdown, just raw JSON):
{{
    "results": [
        {{
            "index": 0,
            "primary_topic": "Topic from list",
            "keywords": ["key", "words"]
        }},
        ...
    ]
}}

Rules:
- Include one result for each numbered text
- primary_topic MUST be from the provided list
- keywords should be 2-3 important words from each text
"""

    user_prompt = f"Classify each numbered text:\n\n{combined[:8000]}"

    results: List[TopicResult] = []
    errors: List[Dict[str, Any]] = []

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        raw = (response.content or "").strip()
        
        import json
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        
        data = json.loads(raw)
        llm_results = data.get("results", [])
        
        # Map results back
        result_by_idx = {r["index"]: r for r in llm_results}
        
        for i, item in enumerate(texts):
            if i in result_by_idx:
                r = result_by_idx[i]
                primary = r.get("primary_topic", "General Questions")
                # Validate
                if primary not in topics:
                    for t in topics:
                        if t.lower() in primary.lower() or primary.lower() in t.lower():
                            primary = t
                            break
                    else:
                        primary = "General Questions"
                
                results.append(TopicResult(
                    text_id=item.get(id_key),
                    primary_topic=primary,
                    keywords=r.get("keywords", []),
                    confidence=0.7,  # Default confidence for batch
                ))
            else:
                results.append(TopicResult(
                    text_id=item.get(id_key),
                    primary_topic="General Questions",
                    confidence=0.0,
                ))
                
    except Exception as e:
        errors.append({"error": str(e), "batch_size": len(texts)})
        for item in texts:
            results.append(TopicResult(
                text_id=item.get(id_key),
                primary_topic="General Questions",
                confidence=0.0,
            ))
    
    return BatchTopicResult(results=results, errors=errors)


def extract_topics_in_chunks(
    texts: List[Dict[str, Any]],
    model: str = "gpt-4o-mini",
    chunk_size: int = 15,
    text_key: str = "content",
    id_key: str = "id",
    allowed_topics: Optional[List[str]] = None,
    max_chars_per_text: int = 400,
    progress_callback: Optional[callable] = None,
) -> BatchTopicResult:
    """
    Extract topics from many texts by processing in chunks.
    
    Args:
        texts: List of dicts containing text and id
        model: OpenAI model name
        chunk_size: Number of texts per LLM call
        text_key: Key for text content
        id_key: Key for text id
        allowed_topics: Optional list of allowed topics
        max_chars_per_text: Max chars per text
        progress_callback: Optional callback(current, total)
    
    Returns:
        BatchTopicResult with all results
    """
    llm = get_llm(model=model)
    all_results: List[TopicResult] = []
    all_errors: List[Dict[str, Any]] = []
    
    total = len(texts)
    for i in range(0, total, chunk_size):
        chunk = texts[i:i + chunk_size]
        batch_result = extract_topics_batch(
            llm=llm,
            texts=chunk,
            text_key=text_key,
            id_key=id_key,
            allowed_topics=allowed_topics,
            max_chars_per_text=max_chars_per_text,
        )
        all_results.extend(batch_result.results)
        all_errors.extend(batch_result.errors)
        
        if progress_callback:
            progress_callback(min(i + chunk_size, total), total)
    
    return BatchTopicResult(results=all_results, errors=all_errors)


def discover_topics(
    texts: List[str],
    model: str = "gpt-4o-mini",
    num_topics: int = 10,
    sample_size: int = 50,
) -> List[str]:
    """
    Discover topics from a sample of texts (useful when you don't have predefined topics).
    
    Args:
        texts: List of text strings
        model: OpenAI model name
        num_topics: Number of topics to discover
        sample_size: Number of texts to sample for discovery
    
    Returns:
        List of discovered topic labels
    """
    import random
    
    # Sample texts
    sample = random.sample(texts, min(sample_size, len(texts)))
    combined = "\n---\n".join(t[:300] for t in sample)
    
    llm = get_llm(model=model)
    
    system_prompt = f"""Analyze these conversation texts and identify the {num_topics} main topics/themes.

Respond in this exact JSON format:
{{
    "topics": [
        "Topic 1 Label",
        "Topic 2 Label",
        ...
    ]
}}

Rules:
- Topics should be clear, concise labels (2-4 words)
- Topics should cover the main themes in the texts
- Topics should be mutually exclusive where possible
- Focus on actionable/meaningful categories
"""

    user_prompt = f"Discover the main topics from these texts:\n\n{combined[:6000]}"

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        raw = (response.content or "").strip()
        
        import json
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        
        data = json.loads(raw)
        return data.get("topics", DEFAULT_TOPICS)
    except Exception:
        return DEFAULT_TOPICS


def summarize_topics(results: List[TopicResult], texts: List[Dict[str, Any]], text_key: str = "content") -> TopicSummary:
    """
    Create a summary of topic distribution.
    
    Args:
        results: List of TopicResult from extraction
        texts: Original texts (for examples)
        text_key: Key for text content
    
    Returns:
        TopicSummary with counts and examples
    """
    from collections import defaultdict
    
    topic_counts: Dict[str, int] = defaultdict(int)
    topic_examples: Dict[str, List[str]] = defaultdict(list)
    
    # Create id -> text mapping
    id_to_text = {}
    for t in texts:
        if "id" in t:
            id_to_text[t["id"]] = (t.get(text_key) or "")[:200]
    
    for r in results:
        topic_counts[r.primary_topic] += 1
        if r.text_id in id_to_text and len(topic_examples[r.primary_topic]) < 3:
            topic_examples[r.primary_topic].append(id_to_text[r.text_id])
    
    return TopicSummary(
        topic_counts=dict(topic_counts),
        topic_examples=dict(topic_examples),
        total_analyzed=len(results),
    )

