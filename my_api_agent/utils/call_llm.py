import os
from openai import OpenAI
from typing import Any

# It's highly recommended to use environment variables for API keys!
# Ensure OPENAI_API_KEY is set in your environment.
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "YOUR_API_KEY_HERE"))

def call_llm(prompt: str, context: Any = None) -> str:
    """
    Calls the configured LLM (defaulting to OpenAI's gpt-4o-mini) with a prompt.

    Args:
        prompt: The main prompt/query for the LLM.
        context: Optional context (not used in this basic version,
                 but could be used for system messages or history).

    Returns:
        The text response from the LLM.
    """
    # Basic implementation using OpenAI chat completions
    # You can adapt this for other models or libraries (Claude, Gemini, local models via Ollama)
    try:
        # Construct messages - a simple user prompt
        # More complex scenarios might involve system prompts or few-shot examples
        messages = [
            {"role": "system", "content": "You are a helpful assistant processing API tasks."},
            {"role": "user", "content": prompt}
        ]
        if context:
            # A very basic way to add context - adjust as needed
            if isinstance(context, list):
                messages = context + messages[1:] # Assume context is message history
            elif isinstance(context, str):
                 messages.insert(1, {"role": "system", "content": f"Additional Context: {context}"})

        print(f"--- Calling LLM ---")
        print(f"Prompt: {prompt}")
        # Consider logging the full messages list if debugging context

        response = client.chat.completions.create(
            # model="gpt-4o", # More powerful, more expensive
            model="gpt-4o-mini", # Cheaper, faster, often sufficient
            messages=messages,
            temperature=0.2, # Lower temperature for more deterministic tasks like API selection
        )
        llm_response = response.choices[0].message.content
        print(f"LLM Response: {llm_response[:100]}...") # Log truncated response
        return llm_response

    except Exception as e:
        print(f"Error calling LLM: {e}")
        # Depending on the error, you might want to raise it or return a specific error message
        # For now, returning an error string
        return f"LLM_ERROR: {e}"

# Example usage (for testing)
if __name__ == "__main__":
    test_prompt = "Explain the concept of an API in simple terms."
    print(f"Testing LLM call with prompt: '{test_prompt}'")

    # Check if API key is potentially missing
    if not os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") == "YOUR_API_KEY_HERE":
        print("\nWARNING: OPENAI_API_KEY environment variable not set or is placeholder.")
        print("LLM call will likely fail. Please set the environment variable.")
        # Optionally skip the test if no key
        # exit()

    response = call_llm(test_prompt)

    print("\nFull Response:")
    print(response)

    if "LLM_ERROR" in response:
        print("\nLLM call failed. Check your API key and network connection.")
    else:
        print("\nLLM call appeared successful.")
