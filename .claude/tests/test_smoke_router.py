import sys
import os
# Add the project root to PYTHONPATH for module resolution
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from ..openrouter_harness.router import OpenRouterHarness
from ..openrouter_harness.models import RouterConfig, RouterCaps
import os

def test_harness_with_tools():
    config = RouterConfig(
        models=["mistralai/mistral-7b-instruct:free"],
        caps=RouterCaps(
            per_attempt_timeout_s=30,
            max_attempts=3,
            total_timeout_s=90
        )
    )
    
    harness = OpenRouterHarness(config)
    
    # Create a test file writing scenario
    test_content = "Test file content"
    messages = [
        {"role": "user", "content": f"Create a file called test_output.txt with this content: {test_content}"}
    ]
    
    try:
        response = harness.request(messages, stream=False)
        print("Harness response:", response)
        
        # Verify file creation
        assert os.path.exists("test_output.txt"), "File was not created"
        with open("test_output.txt", "r") as f:
            content = f.read()
            assert content == test_content, f"File content mismatch: {content} vs {test_content}"
        
        print(" File creation test passed")
        
    finally:
        # Cleanup
        if os.path.exists("test_output.txt"):
            os.remove("test_output.txt")