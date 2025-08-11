import requests
import json
import os
from django.conf import settings

# Constants
GEMINI_URL = settings.GEMINI_URL
GEMINI_API_KEY = settings.GEMINI_API_KEY
MAX_DAILY_TOKENS = 50000

# Load route data
CURRENT_DIR = os.path.dirname(__file__)
ROUTES_FILE = os.path.join(CURRENT_DIR, "routes/routes_with_content.json")
with open(ROUTES_FILE, "r", encoding="utf-8") as f:
    ROUTE_DATA = json.load(f)

# Create classifier-specific data (route-level only)
ROUTE_DATA_FOR_CLASSIFIER = {
    "routes": [
        {
            "url": route["url"],
            "title": route["title"],
            "description": route["description"]
        }
        for route in ROUTE_DATA["routes"]
    ]
}

CLASSIFIER_PROMPT = f"""
You are a URL classifier for Burrowed Literary Magazine's chatbot. Your role is to read the user's question and identify which page URLs are most likely to contain the answer.

Below is the list of available page routes on the platform:
{json.dumps(ROUTE_DATA_FOR_CLASSIFIER, indent=2)}

Your task:
- Carefully analyze the user question.
- Match it against the content and purpose of the listed URLs.
- If the current question alone is unclear, use the previous question and answer for context.
- Return only those URLs that are relevant to the user's query.

The input you receive will include:
PREVIOUS_QUESTION: The user's last question (may be empty).
PREVIOUS_ANSWER: Your last answer to the user (may be empty).
CURRENT_QUESTION: The user’s new question that needs to be catgroerzoed.

Output Format (STRICT):
You must respond in valid JSON, and only in the following format:

{{
  "relevant_urls": ["/url-one", "/url-two"]
}}

If no page matches the query, return:

{{
  "relevant_urls": []
}}

Only return URLs from the list provided above. Do not make up or guess additional paths.
"""


ANSWER_PROMPT = f"""
You are the conversational assistant for Burrowed Literary Magazine’s chatbot. Your job is to read the user’s question, consult only the provided site context, and craft a precise response. If you can point the user to a specific page or section, include navigation guidance; if not, simply answer in chatbot style. 

Available context URLs and their contents:
{json.dumps(ROUTE_DATA_FOR_CLASSIFIER, indent=2)}

If no contact email is found in the content or if you can't answer the user's question, provide: contact@burrowed.org.

Your task:
- Analyze the user’s question.
- Determine if any of the provided URLs contain the answer.
- If relevant, tell the user to navigate to those pages.
- If no context applies, respond conversationally without URLs.

The input you receive will include:
PREVIOUS_QUESTION: The user's last question (may be empty).
PREVIOUS_ANSWER: Your last answer to the user (may be empty).
CURRENT_QUESTION: The user’s new question that needs to be answered.

Output format (STRICT JSON):
If you have one or more page references:
{{
  "answer": "Your concise, user-friendly reply.",
  "supporting_paths": [
    {{
      "url": "/relevant-url",
      "section_id": ["section-id", ...]
    }},
    ...
  ]
}}

If no pages apply:
{{
  "answer": "Your conversational reply without links.",
  "supporting_paths": []
}}
"""


def estimate_tokens(text):
    return max(1, len(text) // 4)

def call_gemini_api(prompt, max_tokens=1000):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.2
        }
    }
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }
    response = requests.post(GEMINI_URL, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()

def get_full_route_data(url):
    """Get complete route data including all sections"""
    for route in ROUTE_DATA["routes"]:
        if route["url"] == url:
            return route
    return None

def validate_classifier_output(output):
    """Validate classifier returns only URLs"""
    try:
        data = json.loads(output)
        if "relevant_urls" not in data:
            return []
        
        # Return only valid URLs that exist in our data
        return [
            url for url in data["relevant_urls"] 
            if any(route["url"] == url for route in ROUTE_DATA_FOR_CLASSIFIER["routes"])
        ]
    except json.JSONDecodeError:
        return []

def build_answer_context(urls):
    """Build complete context for answering agent"""
    context = []
    for url in urls:
        route_data = get_full_route_data(url)
        if route_data:
            context.append({
                "url": route_data["url"],
                "title": route_data["title"],
                "description": route_data["description"],
                "sections": [
                    {
                        "id": section["id"],
                        "label": section["label"],
                        "description": section["description"],
                        "content": section["content"]
                    }
                    for section in route_data["sections"]
                ]
            })
    return context