from google import genai
import os
from flask import current_app
import json

class MCQFactory:
    def __init__(self):
        self.api_key = os.environ.get('GEMINI_API_KEY', 'AIzaSyDjkWPZNbX8Cf6r6MgF5DaysRQ0qttxxJE')
        self.client = genai.Client(api_key=self.api_key)

    def generate_test(self, subject_name, topic, difficulty, num_questions=5):
        # --- AGENT A: THE GENERATOR ---
        generator_prompt = f"""
        Role: Expert Academic Professor in {subject_name}.
        Task: Generate {num_questions} Multiple Choice Questions (MCQs) on the topic: {topic}.
        Difficulty: {difficulty}.
        Format: Return ONLY a valid JSON list of objects with keys: 
        "question", "options" (list of 4 strings), "answer" (the correct string).
        """
        
        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=generator_prompt
        )
        raw_questions = self._clean_json(response.text)

        # --- AGENT B: THE VALIDATOR ---
        validator_prompt = f"""
        Role: Strict Senior Dean and Quality Controller.
        Task: Review the following MCQs for accuracy and clarity. 
        Questions: {raw_questions}
        
        Check for:
        1. Is there exactly one correct answer?
        2. Are the distractors (wrong answers) logical?
        3. Is the difficulty truly '{difficulty}'?
        
        If perfect, return the original JSON. If any question is flawed, fix it.
        Return ONLY the final corrected JSON list.
        """
        
        final_response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=validator_prompt
        )
        return self._clean_json(final_response.text)

    def _clean_json(self, text):
        # Removes markdown backticks if Gemini adds them
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)