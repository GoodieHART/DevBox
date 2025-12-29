"""
Curated collection of programming and tech quotes for the DevBox launcher.
"""

import random

# Programming wisdom quotes
PROGRAMMING_QUOTES = [
    {
        "text": "First, solve the problem. Then, write the code.",
        "author": "John Johnson",
    },
    {
        "text": "The best error message is the one that never shows up.",
        "author": "Thomas Fuchs",
    },
    {
        "text": "Programs must be written for people to read, and only incidentally for machines to execute.",
        "author": "Harold Abelson",
    },
    {
        "text": "The only way to learn a new programming language is by writing programs in it.",
        "author": "Dennis Ritchie",
    },
    {
        "text": "Sometimes it pays to stay in bed on Monday, rather than spending the rest of the week debugging Monday's code.",
        "author": "Dan Salomon",
    },
    {
        "text": "Code is like humor. When you have to explain it, it's bad.",
        "author": "Cory House",
    },
    {"text": "Make it work, make it right, make it fast.", "author": "Kent Beck"},
    {
        "text": "The most disastrous thing that you can ever learn is your first programming language.",
        "author": "Alan Kay",
    },
    {
        "text": "Programming isn't about what you know; it's about what you can figure out.",
        "author": "Chris Pine",
    },
    {
        "text": "The computer was born to solve problems that did not exist before.",
        "author": "Bill Gates",
    },
]

# Tech and startup quotes
TECH_QUOTES = [
    {
        "text": "The best way to predict the future is to invent it.",
        "author": "Alan Kay",
    },
    {
        "text": "Innovation distinguishes between a leader and a follower.",
        "author": "Steve Jobs",
    },
    {
        "text": "Your most unhappy customers are your greatest source of learning.",
        "author": "Bill Gates",
    },
    {
        "text": "The Internet is becoming the town square for the global village of tomorrow.",
        "author": "Bill Gates",
    },
    {
        "text": "Technology is best when it brings people together.",
        "author": "Matt Mullenweg",
    },
]

# Fun and motivational quotes
FUN_QUOTES = [
    {
        "text": "There are only 10 types of people in the world: those who understand binary, and those who don't.",
        "author": "Anonymous",
    },
    {
        "text": "A good programmer is someone who always looks both ways before crossing a one-way street.",
        "author": "Doug Linder",
    },
    {
        "text": "I have not failed. I've just found 10,000 ways that won't work.",
        "author": "Thomas Edison",
    },
    {
        "text": "The future belongs to those who believe in the beauty of their dreams.",
        "author": "Eleanor Roosevelt",
    },
]

# Success celebration quotes
SUCCESS_QUOTES = [
    {
        "text": "Success is not final, failure is not fatal: It is the courage to continue that counts.",
        "author": "Winston Churchill",
    },
    {
        "text": "The only way to do great work is to love what you do.",
        "author": "Steve Jobs",
    },
    {
        "text": "Believe you can and you're halfway there.",
        "author": "Theodore Roosevelt",
    },
]

# Loading and progress quotes
LOADING_QUOTES = [
    {
        "text": "Patience is a virtue... especially in programming.",
        "author": "Anonymous",
    },
    {
        "text": "Good things come to those who wait... and have good code.",
        "author": "Anonymous",
    },
    {
        "text": "While we're waiting, remember: a good programmer looks both ways before crossing a one-way street.",
        "author": "Doug Linder",
    },
]

# Organize quotes by category
QUOTES_BY_CATEGORY = {
    "programming": PROGRAMMING_QUOTES,
    "tech": TECH_QUOTES,
    "fun": FUN_QUOTES,
    "success": SUCCESS_QUOTES,
    "loading": LOADING_QUOTES,
    "startup": PROGRAMMING_QUOTES + TECH_QUOTES,  # Combined for startup
    "general": PROGRAMMING_QUOTES + TECH_QUOTES + FUN_QUOTES,
}


def get_random_quote(category="general"):
    """
    Get a random quote from the specified category.

    Args:
        category (str): The category of quotes to choose from

    Returns:
        dict: A quote dictionary with 'text' and 'author' keys, or None if category not found
    """
    if category not in QUOTES_BY_CATEGORY:
        category = "general"

    quotes = QUOTES_BY_CATEGORY[category]
    if not quotes:
        return None

    return random.choice(quotes)


def get_quote_count(category=None):
    """
    Get the count of quotes in a category or all categories.

    Args:
        category (str, optional): Specific category to count, or None for all

    Returns:
        int or dict: Quote count(s)
    """
    if category:
        return len(QUOTES_BY_CATEGORY.get(category, []))
    else:
        return {cat: len(quotes) for cat, quotes in QUOTES_BY_CATEGORY.items()}


# For testing
if __name__ == "__main__":
    print("DevBox Quotes Test:")
    print(f"Total quotes: {sum(get_quote_count().values())}")

    for category in QUOTES_BY_CATEGORY.keys():
        quote = get_random_quote(category)
        if quote:
            print(f"\n{category.title()} Quote:")
            print(f'"{quote["text"]}"')
            print(f"— {quote['author']}")
