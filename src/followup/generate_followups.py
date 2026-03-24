import os
import torch
from transformers import T5Tokenizer, T5ForConditionalGeneration
from src.core.logging_config import logger

def generate_followups(category, initial_question, conversation, use_model=False):
    if use_model:
        model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../followup_model'))
        if os.path.exists(model_path):
            try:
                tokenizer = T5Tokenizer.from_pretrained(model_path)
                model = T5ForConditionalGeneration.from_pretrained(model_path)
                prompt = f"Category: {category}. Initial question: {initial_question}. Conversation: {conversation}"
                inputs = tokenizer.encode("summarize: " + prompt, return_tensors="pt", max_length=512, truncation=True)
                outputs = model.generate(inputs, max_length=128, num_return_sequences=1)
                res = tokenizer.decode(outputs[0], skip_special_tokens=True)
                return [q.strip() for q in res.split('|') if q.strip()]
            except Exception as e:
                logger.error(f"Error loading T5 model: {e}")
    
    # Rule-based fallback
    question_lower = initial_question.lower()
    if 'password' in question_lower:
        return ["What browser are you using?", "Did you receive a reset email?", "Any error message seen?"]
    if 'login' in question_lower or 'account' in question_lower:
        return ["Are you using the mobile app or web?", "When did you first notice this issue?"]
    
    return ["Could you provide more details about the issue?", "What steps have you already tried?"]
