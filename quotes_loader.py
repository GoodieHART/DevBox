"""
Quotes Management Module for DevBox Launcher

This module handles loading and managing programming quotes from JSON data file.
Provides error handling and fallback quotes for robust operation.

Author: DevBox Launcher
"""

import json
import random
import os
from typing import Dict, List, Optional


def load_quotes(quotes_file: str = "quotes.json") -> List[Dict[str, str]]:
    """
    Load programming quotes from JSON file with error handling and fallback.
    
    Args:
        quotes_file: Path to the quotes JSON file (default: "quotes.json")
        
    Returns:
        List of quote dictionaries with 'text' and 'author' keys
    """
    fallback_quotes = [
        {"text": "Code is like humor. When you have to explain it, it's bad.", "author": "Cory House"},
        {"text": "First, solve the problem. Then, write the code.", "author": "John Johnson"},
        {"text": "Make it work, make it right, make it fast.", "author": "Kent Beck"}
    ]
    
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        quotes_path = os.path.join(script_dir, quotes_file)
        
        if not os.path.exists(quotes_path):
            return fallback_quotes
            
        with open(quotes_path, 'r', encoding='utf-8') as f:
            quotes = json.load(f)
            
        if not isinstance(quotes, list) or not quotes:
            return fallback_quotes
            
        for quote in quotes:
            if not isinstance(quote, dict) or 'text' not in quote or 'author' not in quote:
                return fallback_quotes
                
        return quotes
        
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return fallback_quotes


def get_random_quote(quotes_file: str = "quotes.json") -> Dict[str, str]:
    """
    Get a random programming quote from the loaded quotes.
    
    Args:
        quotes_file: Path to the quotes JSON file (default: "quotes.json")
        
    Returns:
        A random quote dictionary with 'text' and 'author' keys
    """
    quotes = load_quotes(quotes_file)
    return random.choice(quotes)


def format_quote(quote: Dict[str, str]) -> str:
    """
    Format a quote dictionary into a displayable string.
    
    Args:
        quote: Quote dictionary with 'text' and 'author' keys
        
    Returns:
        Formatted quote string ready for display
    """
    return f'"{quote["text"]}"\n\n— {quote["author"]}'