"""
Semantic Analysis Utilities
===========================

LLM-based sentiment analysis for conversation messages using LangChain + OpenAI.
"""

import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

# Load environment variables
load_dotenv()


class SentimentLabel(str, Enum):
    """Sentiment classification labels."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


@dataclass
class SentimentResult:
    """Result of sentiment analysis for a single text."""
    text_id: Any
    sentiment: SentimentLabel
    confidence: float  # 0.0 to 1.0
    explanation: str
    raw_response: str


@dataclass
class BatchSentimentResult:
    """Result of batch sentiment analysis."""
    results: List[SentimentResult]
    errors: List[Dict[str, Any]]


def get_llm(model: str = "gpt-4o-mini", temperature: float = 0.1) -> ChatOpenAI:
    """
    Get a configured ChatOpenAI instance.
    
    Args:
        model: OpenAI model name
        temperature: Sampling temperature (lower = more deterministic)
    
    Returns:
        Configured ChatOpenAI instance
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables")
    return ChatOpenAI(model=model, temperature=temperature, api_key=api_key)


def analyze_sentiment_single(
    llm: ChatOpenAI,
    text: str,
    text_id: Any = None,
) -> SentimentResult:
    """
    Analyze sentiment of a single text using LLM.
    
    Args:
        llm: Configured ChatOpenAI instance
        text: Text to analyze
        text_id: Optional identifier for the text
    
    Returns:
        SentimentResult with classification and confidence
    """
    system_prompt = """You are a sentiment analysis expert. Analyze the sentiment of the given text.

Respond in this exact JSON format (no markdown, just raw JSON):
{
    "sentiment": "positive" | "negative" | "neutral" | "mixed",
    "confidence": 0.0-1.0,
    "explanation": "Brief explanation of why this sentiment was chosen"
}

Rules:
- "positive": Text expresses satisfaction, happiness, gratitude, or positive emotions
- "negative": Text expresses frustration, disappointment, anger, or negative emotions
- "neutral": Text is informational, factual, or lacks emotional content
- "mixed": Text contains both positive and negative sentiments
- Confidence should reflect how clear the sentiment is (1.0 = very clear, 0.5 = ambiguous)
"""

    user_prompt = f"Analyze the sentiment of this text:\n\n{text[:2000]}"

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        raw = (response.content or "").strip()
        
        # Parse JSON response
        import json
        # Handle potential markdown code blocks
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        
        data = json.loads(raw)
        sentiment_str = data.get("sentiment", "neutral").lower()
        
        # Map to enum
        sentiment_map = {
            "positive": SentimentLabel.POSITIVE,
            "negative": SentimentLabel.NEGATIVE,
            "neutral": SentimentLabel.NEUTRAL,
            "mixed": SentimentLabel.MIXED,
        }
        sentiment = sentiment_map.get(sentiment_str, SentimentLabel.NEUTRAL)
        
        return SentimentResult(
            text_id=text_id,
            sentiment=sentiment,
            confidence=float(data.get("confidence", 0.5)),
            explanation=data.get("explanation", ""),
            raw_response=raw,
        )
    except Exception as e:
        return SentimentResult(
            text_id=text_id,
            sentiment=SentimentLabel.NEUTRAL,
            confidence=0.0,
            explanation=f"Error: {str(e)}",
            raw_response="",
        )


def analyze_sentiment_batch(
    llm: ChatOpenAI,
    texts: List[Dict[str, Any]],
    text_key: str = "content",
    id_key: str = "id",
    max_chars_per_text: int = 500,
) -> BatchSentimentResult:
    """
    Analyze sentiment of multiple texts in a single LLM call for efficiency.
    
    Args:
        llm: Configured ChatOpenAI instance
        texts: List of dicts containing text and id
        text_key: Key for text content in each dict
        id_key: Key for text id in each dict
        max_chars_per_text: Max characters per text to send
    
    Returns:
        BatchSentimentResult with all results
    """
    if not texts:
        return BatchSentimentResult(results=[], errors=[])
    
    # Prepare numbered list of texts
    numbered_texts = []
    for i, item in enumerate(texts):
        text = (item.get(text_key) or "")[:max_chars_per_text]
        numbered_texts.append(f"[{i}] {text}")
    
    combined = "\n\n".join(numbered_texts)
    
    system_prompt = """You are a sentiment analysis expert. Analyze the sentiment of each numbered text.

Respond in this exact JSON format (no markdown, just raw JSON):
{
    "results": [
        {
            "index": 0,
            "sentiment": "positive" | "negative" | "neutral" | "mixed",
            "confidence": 0.0-1.0
        },
        ...
    ]
}

Rules:
- Include one result for each numbered text [0], [1], etc.
- "positive": satisfaction, happiness, gratitude
- "negative": frustration, disappointment, anger
- "neutral": informational, factual, no strong emotion
- "mixed": both positive and negative sentiments
"""

    user_prompt = f"Analyze the sentiment of each numbered text:\n\n{combined[:8000]}"

    results: List[SentimentResult] = []
    errors: List[Dict[str, Any]] = []

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
        llm_results = data.get("results", [])
        
        sentiment_map = {
            "positive": SentimentLabel.POSITIVE,
            "negative": SentimentLabel.NEGATIVE,
            "neutral": SentimentLabel.NEUTRAL,
            "mixed": SentimentLabel.MIXED,
        }
        
        # Map results back to original items
        result_by_idx = {r["index"]: r for r in llm_results}
        
        for i, item in enumerate(texts):
            if i in result_by_idx:
                r = result_by_idx[i]
                sentiment_str = r.get("sentiment", "neutral").lower()
                results.append(SentimentResult(
                    text_id=item.get(id_key),
                    sentiment=sentiment_map.get(sentiment_str, SentimentLabel.NEUTRAL),
                    confidence=float(r.get("confidence", 0.5)),
                    explanation="",
                    raw_response="",
                ))
            else:
                # Missing result, default to neutral
                results.append(SentimentResult(
                    text_id=item.get(id_key),
                    sentiment=SentimentLabel.NEUTRAL,
                    confidence=0.0,
                    explanation="Missing from LLM response",
                    raw_response="",
                ))
                
    except Exception as e:
        errors.append({"error": str(e), "batch_size": len(texts)})
        # Fallback: return neutral for all
        for item in texts:
            results.append(SentimentResult(
                text_id=item.get(id_key),
                sentiment=SentimentLabel.NEUTRAL,
                confidence=0.0,
                explanation=f"Batch error: {str(e)}",
                raw_response="",
            ))
    
    return BatchSentimentResult(results=results, errors=errors)


def analyze_sentiment_in_chunks(
    texts: List[Dict[str, Any]],
    model: str = "gpt-4o-mini",
    chunk_size: int = 20,
    text_key: str = "content",
    id_key: str = "id",
    max_chars_per_text: int = 500,
    progress_callback: Optional[callable] = None,
) -> BatchSentimentResult:
    """
    Analyze sentiment of many texts by processing in chunks.
    
    Args:
        texts: List of dicts containing text and id
        model: OpenAI model name
        chunk_size: Number of texts per LLM call
        text_key: Key for text content in each dict
        id_key: Key for text id in each dict
        max_chars_per_text: Max characters per text
        progress_callback: Optional callback(current, total) for progress updates
    
    Returns:
        BatchSentimentResult with all results
    """
    llm = get_llm(model=model)
    all_results: List[SentimentResult] = []
    all_errors: List[Dict[str, Any]] = []
    
    total = len(texts)
    for i in range(0, total, chunk_size):
        chunk = texts[i:i + chunk_size]
        batch_result = analyze_sentiment_batch(
            llm=llm,
            texts=chunk,
            text_key=text_key,
            id_key=id_key,
            max_chars_per_text=max_chars_per_text,
        )
        all_results.extend(batch_result.results)
        all_errors.extend(batch_result.errors)
        
        if progress_callback:
            progress_callback(min(i + chunk_size, total), total)
    
    return BatchSentimentResult(results=all_results, errors=all_errors)

