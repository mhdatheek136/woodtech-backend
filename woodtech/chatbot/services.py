import json
import re
import requests
import time
from django.conf import settings
from django.utils import timezone
from datetime import datetime
from woodtech.models import Conversation

class GeminiService:
    def __init__(self):
        self.url = settings.GEMINI_URL
        self.api_key = settings.GEMINI_API_KEY
        self.max_daily_tokens = getattr(settings, 'MAX_DAILY_TOKENS', 50000)

    def call_api(self, prompt, max_tokens=1000, agent_type="answer"):
        start_time = time.time()
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.2
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }
        
        response = requests.post(self.url, json=payload, headers=headers)
        response.raise_for_status()
        response_data = response.json()
        
        processing_time = time.time() - start_time
        
        # Extract token counts
        usage_metadata = response_data.get('usageMetadata', {})
        prompt_tokens = usage_metadata.get('promptTokenCount', 0)
        completion_tokens = usage_metadata.get('candidatesTokenCount', 0)
        total_tokens = usage_metadata.get('totalTokenCount', 0)
        
        return {
            'text': response_data['candidates'][0]['content']['parts'][0]['text'],
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'processing_time': processing_time,
            'raw_response': response_data
        }

class ChatbotService:
    def __init__(self):
        self.gemini_service = GeminiService()
        self.route_data = self._load_route_data()
        self.route_data_for_classifier = self._create_classifier_data()
        
    def _load_route_data(self):
        import os
        import json
        current_dir = os.path.dirname(__file__)
        routes_file = os.path.join(current_dir, "../routes/routes_with_content.json")
        with open(routes_file, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _create_classifier_data(self):
        return {
            "routes": [
                {
                    "url": route["url"],
                    "title": route["title"],
                    "description": route["description"]
                }
                for route in self.route_data["routes"]
            ]
        }
    
    def get_classifier_prompt(self, previous_prompt, previous_answer, current_question):
        classifier_prompt = f"""
You are a URL classifier for Burrowed Literary Magazine's chatbot. Your role is to read the user's question and identify which page URLs are most likely to contain the answer.

Below is the list of available page routes on the platform:
{json.dumps(self.route_data_for_classifier, indent=2)}

Your task:
- Carefully analyze the user question.
- Match it against the content and purpose of the listed URLs.
- If the current question alone is unclear, use the previous question and answer for context.
- Return only those URLs that are relevant to the user's query.

The input you receive will include:
PREVIOUS_QUESTION: The user's last question (may be empty).
PREVIOUS_ANSWER: Your last answer to the user (may be empty).
CURRENT_QUESTION: The user's new question that needs to be categorized.

Use PREVIOUS_QUESTION and PREVIOUS_ANSWER only if the CURRENT_QUESTION requires knowledge from prior context. Otherwise, answer based solely on the CURRENT_QUESTION.

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
        
        return (
            f"{classifier_prompt}\n\n"
            f"PREVIOUS_QUESTION: {previous_prompt}\n"
            f"PREVIOUS_ANSWER: {previous_answer}\n"
            f"CURRENT_QUESTION: {current_question}\n"
        )
    
    def get_answer_prompt(self, previous_prompt, previous_answer, current_question, context):
        today = datetime.now().strftime("%Y-%m-%d")
        
        answer_prompt = f"""
You are the conversational assistant for Burrowed Literary Magazine's chatbot. Your job is to read the user's question, consult only the provided site context, and craft a precise response. If you can point the user to a specific page or section, include navigation guidance; if not, simply answer in chatbot style. 

Available context URLs and their contents:
{json.dumps(self.route_data_for_classifier, indent=2)}

If no contact email is found in the content or if you can't answer the user's question, provide: contact@burrowed.org.

Your task:
- Analyze the user's question.
- Determine if any of the provided URLs contain the answer.
- If the answer exists in the context, always answer the user's question directly.
- If relevant, also tell the user which page/section to navigate to.
- Only when no context applies, respond conversationally without URLs.

The input you receive will include:
PREVIOUS_QUESTION: The user's last question (may be empty).
PREVIOUS_ANSWER: Your last answer to the user (may be empty).
CURRENT_QUESTION: The user's new question that needs to be answered.
CURRENT_DATE: Provided for use only if the user's question requires knowing today's date.

Use PREVIOUS_QUESTION and PREVIOUS_ANSWER only if the CURRENT_QUESTION requires knowledge from prior context. Otherwise, answer based solely on the CURRENT_QUESTION.

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
        
        return (
            f"{answer_prompt}\n\n"
            f"CURRENT_DATE: {today}\n"
            f"PREVIOUS_QUESTION: {previous_prompt}\n"
            f"PREVIOUS_ANSWER: {previous_answer}\n"
            f"CURRENT_QUESTION: {current_question}\n"
            f"CONTEXT:\n{context}"
        )
    
    def validate_classifier_output(self, output):
        try:
            data = json.loads(output)
            if "relevant_urls" not in data:
                return []
            
            return [
                url for url in data["relevant_urls"] 
                if any(route["url"] == url for route in self.route_data_for_classifier["routes"])
            ]
        except json.JSONDecodeError:
            return []
    
    def get_full_route_data(self, url):
        for route in self.route_data["routes"]:
            if route["url"] == url:
                return route
        return None
    
    def build_answer_context(self, urls):
        context = []
        for url in urls:
            route_data = self.get_full_route_data(url)
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
    
    def record_conversation(self, ip_address, user_input, agent_type, gemini_response, agent_input=""):
        Conversation.objects.create(
            ip_address=ip_address,
            user_input=user_input,
            agent_type=agent_type,
            prompt_tokens=gemini_response['prompt_tokens'],
            completion_tokens=gemini_response['completion_tokens'],
            total_tokens=gemini_response['total_tokens'],
            processing_time=gemini_response['processing_time'],
            agent_input=agent_input,
            agent_output=gemini_response['text']
        )
    
    def clean_answer_output(self, output):
        cleaned_output = re.sub(r"^```(?:json)?|```$", "", output.strip(), flags=re.MULTILINE)
        cleaned_output = "\n".join(
            line.split("|", 1)[-1].strip() if "|" in line else line
            for line in cleaned_output.splitlines()
        )
        return cleaned_output