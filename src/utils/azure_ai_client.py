"""
Azure AI Client
--------------

Diese Datei implementiert einen einheitlichen Client für Azure AI-Dienste, der eine konsistente
Schnittstelle für verschiedene Azure-Modelltypen bereitstellt:

1. Azure OpenAI-Modelle (gpt-4.1, gpt-4o, o3-mini, etc.) mit multimodalen Fähigkeiten
2. Azure AI Foundation-Modelle (DeepSeek-V3, Llama-3.3, Mistral-Large, Phi-4) nur für Text

Hauptfunktionen:
- Einheitliche API für alle Azure AI-Modelltypen über die Methode `completion()`
- Unterstützung für Bilder in Prompts (nur für OpenAI-Modelle)
- Spezielle Behandlung für OpenAI Reasoning-Modelle (o3, o3-mini, etc.) inklusive 'reasoning_effort'
- Strukturierte JSON-Ausgabe für unterstützte Modelle
- Automatische Clientinitialisierung je nach Modellanforderung
- Gruppierte Auflistung verfügbarer Modelle

Die Klasse verwendet folgende Azure-Clients im Hintergrund:
- AzureOpenAI-Client für OpenAI-Modelle (unterstützt Text und Bilder)
- ChatCompletionsClient für AI Foundation-Modelle (nur Text)

Beispielnutzung:
```python
# Initialisierung des Clients
client = AzureAIClient(system_prompt="Du bist ein hilfreicher Assistent.")

# Anfrage an ein Reasoning-Modell mit reasoning_effort
response = client.completion(
    model_name="o3-mini",
    user_prompt="Löse dieses komplexe Problem...",
    reasoning_effort="low"
)
```

Voraussetzungen:
- Azure OpenAI API-Schlüssel und Endpunkt in Umgebungsvariablen:
  - AZURE_OPENAI_API_KEY
  - AZURE_OPENAI_API_VERSION
  - AZURE_OPENAI_ENDPOINT
- Azure AI Foundation API-Schlüssel und Endpunkt in Umgebungsvariablen:
  - AZURE_AIFOUNDRY_API_KEY
  - AZURE_AIFOUNDRY_ENDPOINT

"""

import os
import base64
from typing import Dict, Optional, Union, List, Any
from openai import AzureOpenAI
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential


class AzureAIClient:
    """
    Unified client for Azure OpenAI and Azure AI Foundation models.

    This class handles the interaction with both Azure OpenAI models (including multimodal capabilities)
    and Azure AI Foundation models in a unified interface.
    """

    # Define available model groups
    AZURE_OPENAI_MODELS = [
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4o",
        "o3-mini",
        "o4-mini"]

    AZURE_AI_FOUNDATION_MODELS = [
        "DeepSeek-V3-0324",
        "DeepSeek-R1-0528",
        "Llama-3.3-70B-Instruct",
        "Llama-4-Maverick-17B-128E-Instruct-FP8",
        "mistral-medium-2505",
        "Phi-4"]

    # Define OpenAI reasoning models which need special handling
    OPENAI_REASONING_MODELS = [
        "o3-mini",
        "o4-mini"]

    def __init__(self, system_prompt: str = "You are a helpful assistant."):
        """
        Initialize the AzureAIClient.

        Args:
            system_prompt: The system prompt to use for all conversations
        """
        self.system_prompt = system_prompt

        # Initialize clients
        self.openai_client = None
        self.foundation_client = None

    def get_available_models(self) -> Dict[str, List[str]]:
        """
        Get all available models grouped by API type.

        Returns:
            Dictionary with model groups and their available models
        """
        return {
            "Azure OpenAI (multimodal)": self.AZURE_OPENAI_MODELS,
            "Azure AI Foundation (text-only)": self.AZURE_AI_FOUNDATION_MODELS
        }

    def _initialize_openai_client(self):
        """Initialize the Azure OpenAI client if not already initialized."""
        if self.openai_client is None:
            self.openai_client = AzureOpenAI(
                api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION"),
                azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
                timeout=60.0
            )

    def _initialize_foundation_client(self):
        """Initialize the Azure AI Foundation client if not already initialized."""
        if self.foundation_client is None:
            self.foundation_client = ChatCompletionsClient(
                endpoint=os.environ.get("AZURE_AIFOUNDRY_ENDPOINT"),
                credential=AzureKeyCredential(os.environ.get("AZURE_AIFOUNDRY_API_KEY")),
            )

    def _encode_image(self, image_path: str) -> str:
        """Encode an image to base64.

        Args:
            image_path: Path to the image file

        Returns:
            Base64 encoded image string
        """
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def _is_reasoning_model(self, model_name: str) -> bool:
        """
        Check if the model is an OpenAI reasoning model requiring special handling.

        Args:
            model_name: The name of the model to check

        Returns:
            True if the model is a reasoning model, False otherwise
        """
        return any(model_name.startswith(rm) for rm in self.OPENAI_REASONING_MODELS)

    def completion(self,
                model_name: str,
                user_prompt: str,
                image_path: Optional[str] = None,
                temperature: float = 0,
                max_tokens: int = 2048,
                response_format: Optional[Dict[str, str]] = None,
                reasoning_effort: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a completion using the specified model.

        Args:
            model_name: The name of the model to use
            user_prompt: The user's prompt
            image_path: Optional path to an image (for multimodal models)
            temperature: Temperature for generation (0-1)
            max_tokens: Maximum tokens to generate
            response_format: Optional dict specifying output format {'type': 'text'} or {'type': 'json_object'}
            reasoning_effort: Optional reasoning effort for reasoning models (e.g., 'low', 'auto').

        Returns:
            Dictionary containing 'text' (the generated text) and 'usage' (token usage stats)
        """
        if model_name in self.AZURE_OPENAI_MODELS or self._is_reasoning_model(model_name):
            return self._generate_openai(model_name, user_prompt, image_path, temperature, max_tokens, response_format, reasoning_effort)
        elif model_name in self.AZURE_AI_FOUNDATION_MODELS:
            if image_path:
                raise ValueError(f"Model {model_name} does not support images. Use one of {self.AZURE_OPENAI_MODELS} for multimodal capabilities.")
            return self._generate_foundation(model_name, user_prompt, temperature, max_tokens, response_format)
        else:
            available_models = self.AZURE_OPENAI_MODELS + self.AZURE_AI_FOUNDATION_MODELS
            raise ValueError(f"Unknown model: {model_name}. Available models: {available_models}")

    def _generate_openai(self,
                        model_name: str,
                        user_prompt: str,
                        image_path: Optional[str] = None,
                        temperature: float = 0,
                        max_tokens: int = 2048,
                        response_format: Optional[Dict[str, str]] = None,
                        reasoning_effort: Optional[str] = None) -> Dict[str, Any]:
        """Generate using Azure OpenAI."""
        self._initialize_openai_client()

        # Prepare the messages
        messages = [
            {
                "role": "system",
                "content": self.system_prompt
            }
        ]

        # Add user message with or without image
        if image_path:
            base64_image = self._encode_image(image_path)
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "high"
                        }
                    }
                ]
            })
        else:
            messages.append({
                "role": "user",
                "content": user_prompt
            })

        # Prepare API call parameters
        kwargs = {
            "model": model_name,
            "messages": messages,
        }

        # Special handling for OpenAI reasoning models
        if self._is_reasoning_model(model_name):
            # Reasoning models require temperature=1.0 regardless of input
            kwargs["temperature"] = 1.0
            # Reasoning models use max_completion_tokens instead of max_tokens
            kwargs["max_completion_tokens"] = max_tokens
            # Add reasoning_effort if provided
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort
        else:
            # For regular models, use the provided values
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens

        # Add response_format if provided
        if response_format:
            kwargs["response_format"] = response_format

        # Make the API call
        response = self.openai_client.chat.completions.create(**kwargs)

        # Extract and return the results
        return {
            "text": response.choices[0].message.content,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }

    def _generate_foundation(self,
                           model_name: str,
                           user_prompt: str,
                           temperature: float = 0,
                           max_tokens: int = 2048,
                           response_format: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Generate using Azure AI Foundation."""
        self._initialize_foundation_client()

        # Use default response format if none provided
        if response_format is None:
            response_format = {"type": "text"}

        # Prepare the system prompt - add JSON instruction if needed
        system_prompt = self.system_prompt
        if response_format.get("type") == "json_object" and model_name in ["DeepSeek-V3-0324", "Llama-3.3-70B-Instruct", "Mistral-Large-2411"]:
            system_prompt = f"{system_prompt} WICHTIG: Die Ausgabe darf ausschließlich im JSON-Format gemäß der Format Vorgabe im User Prompt erfolgen!"

        # Prepare the messages
        messages = [
            SystemMessage(content=system_prompt),
            UserMessage(content=user_prompt)
        ]

        # Prepare API call parameters
        kwargs = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "model": model_name
        }

        # Add response_format if the model supports it and it's requested to be JSON
        if response_format.get("type") == "json_object" and model_name in ["DeepSeek-V3-0324", "Llama-3.3-70B-Instruct", "Mistral-Large-2411"]:
            kwargs["response_format"] = response_format.get("type")

        # Make the API call
        response = self.foundation_client.complete(**kwargs)

        # Extract and return the results
        return {
            "text": response.choices[0].message.content,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
