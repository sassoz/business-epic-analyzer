import json
import re

class LLMJsonParser:
    def __init__(self):
        self.json_pattern = re.compile(r'```json\s*(.*?)\s*```', re.DOTALL)
        self.curly_pattern = re.compile(r'(\{.*\})', re.DOTALL)
    
    def extract_and_parse_json(self, text):
        """
        Extracts and parses JSON from LLM output text.
        
        Args:
            text (str): The text output from an LLM that might contain JSON
            
        Returns:
            dict: The parsed JSON data or empty dict if parsing fails
        """
        # Method 1: Try direct parsing (in case it's already valid JSON)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Method 2: Look for JSON code blocks
        json_match = self.json_pattern.search(text)
        if json_match:
            json_text = json_match.group(1)
            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                pass
        
        # Method 3: Look for text between curly braces
        curly_match = self.curly_pattern.search(text)
        if curly_match:
            json_text = curly_match.group(1)
            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                pass
        
        # If all methods fail, attempt to clean and fix the JSON
        return self._clean_and_fix_json(text)
    
    def _clean_and_fix_json(self, text):
        """
        Attempts to clean and fix malformed JSON.
        
        Args:
            text (str): Text that might contain malformed JSON
            
        Returns:
            dict: Parsed JSON or empty dict if all attempts fail
        """
        # Try to extract content between outermost curly braces
        try:
            # Find the first opening brace and last closing brace
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_text = text[start_idx:end_idx+1]
                
                # Common fixes for malformed JSON
                # 1. Fix unquoted keys
                json_text = re.sub(r'([{,])\s*([a-zA-Z0-9_]+)\s*:', r'\1"\2":', json_text)
                
                # 2. Fix single quoted strings
                json_text = re.sub(r"'([^']*)'", r'"\1"', json_text)
                
                # 3. Remove trailing commas
                json_text = re.sub(r',\s*([}\]])', r'\1', json_text)
                
                # Try to parse the fixed JSON
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        
        # Return empty dict if all attempts fail
        return {}

# Example usage
def parse_llm_json(result_text):
    parser = LLMJsonParser()
    result_json = parser.extract_and_parse_json(result_text)
    return result_json

# Modified version of your existing code
def get_structured_json(prompt, model, litellm_completion):
    try:
        # litellm aufrufen
        response = litellm_completion(
            model=model,
            messages=[
                {"role": "system", "content": "Du bist ein hilfreicher Assistent, der Informationen aus Texten extrahiert und in strukturiertes JSON-Format umwandelt."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=8000,
            num_retries=3
        )
        result = response['choices'][0]['message']['content']
        
        # Parse the result into JSON
        result_json = parse_llm_json(result)
        
        return result_json
    except Exception as e:
        print(f"Error: {e}")
        return {}