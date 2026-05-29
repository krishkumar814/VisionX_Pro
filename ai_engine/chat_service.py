from google import genai
import os
from flask import current_app
import fitz
import re

class SubjectAgent:
    def __init__(self):
        self.api_key = os.environ.get('GEMINI_API_KEY', 'AIzaSyDjkWPZNbX8Cf6r6MgF5DaysRQ0qttxxJE')
        self.client = genai.Client(api_key=self.api_key)

    def _chunk_and_retrieve(self, file_path, user_query):
        try:
            doc = fitz.open(file_path)
            text = ""
            for page in doc: 
                text += page.get_text() + "\n"
            
            # 1. Chunking text into ~400 word chunks
            words = text.split()
            chunk_size = 400
            chunks = [' '.join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
            
            # 2. Extract keywords from user query
            stopwords = {"a", "an", "the", "is", "are", "am", "was", "were", "of", "in", "to", "for", "with", "on", "at", "by", "from", "up", "about", "into", "over", "after", "how", "what", "why", "when", "where", "who", "which", "that", "this", "these", "those", "and", "or", "but", "not", "it", "as", "be", "do", "does", "did", "can", "could", "would", "should", "explain", "describe", "tell", "me"}
            query_words = re.findall(r'\b\w+\b', user_query.lower())
            keywords = {w for w in query_words if w not in stopwords}
            
            # 3. Match keywords and select top chunks
            def score_chunk(chunk):
                chunk_words = set(re.findall(r'\b\w+\b', chunk.lower()))
                return sum(1 for kw in keywords if kw in chunk_words)
            
            if keywords:
                ranked_chunks = sorted(chunks, key=score_chunk, reverse=True)
            else:
                ranked_chunks = chunks
            
            # 4. Top 3 chunks
            top_chunks = ranked_chunks[:3]
            return "\n\n--- RELEVANT EXTRACT ---\n\n".join(top_chunks)
            
        except Exception as e:
            print(f"Failed to read PDF for RAG context: {e}")
            return ""

    def ask_general_mode(self, question, subject_name):
        prompt = f"""
        You are an expert AI Learning Assistant for the subject: {subject_name}.
        User Question: {question}
        Instructions:
        Provide a very clear, highly simplified, and easy-to-understand explanation for a student.
        """
        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            if response.text:
                return response.text
            return "The AI returned an empty response. Please try rephrasing your question."
        except Exception as e:
            print(f"General Agent Error: {e}")
            return "The AI is currently experiencing high loads or network issues. Please try again."

    def ask_document_mode(self, question, subject_name, file_path):
        context_text = self._chunk_and_retrieve(file_path, question)
        
        if not context_text:
            return self.ask_general_mode(question, subject_name)
            
        final_prompt = f"""
        You are an expert AI Learning Assistant for the subject: {subject_name}.
        You are provided with extracts from the student's textbook/PDF.
        
        Extracted Context:
        {context_text}
        
        User Question: {question}
        
        Instructions:
        1. Answer the question based primarily on the provided context. 
        2. If the context doesn't fully answer the question, use your general knowledge.
        3. Make the explanation incredibly clear and easy to understand for a beginner student.
        4. Use formatting (like bullet points or bold text) to aid readability.
        """
        
        try:
            final_answer = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=final_prompt
            )
            if final_answer.text:
                return final_answer.text
            return "The AI returned an empty response. Please try rephrasing your question."
        except Exception as e:
            print(f"Document Agent Error: {e}")
            return "The AI is currently experiencing high loads or network issues. Please try again."