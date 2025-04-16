import unittest
from unittest.mock import MagicMock, patch
import time
import json

# Assuming this is the correct import path for the tool creation function
from app import create_recipes_self_query_tool
from gutenberg.recipes_storage_and_retrieval_v2 import (
    build_outputs
)

class TestPerformance(unittest.TestCase):

    def setUp(self):
        # Mock components
        self.mock_llm = MagicMock()
        self.mock_vector_store = MagicMock()
        self.mock_structured_query_translator = MagicMock()

        # Sample recipe document
        self.sample_recipe = [
            {"page_content": "Recipe content", "metadata": {"recipe_name": "Sample Recipe"}}
        ]

    def mock_generation_output(self, input_data):
        # Simulate both text and token usage metadata
        return {
            "text": input_data.get("text", ""),
            "metadata": {
                "input_tokens": input_data.get("input_tokens", 10),
                "output_tokens": input_data.get("output_tokens", 20)
            }
        }

    @patch('gutenberg.recipes_storage_and_retrieval_v2.perform_self_query_retrieval')
    @patch('gutenberg.recipes_storage_and_retrieval_v2.build_outputs')
    def test_parallel_processing_performance_and_token_usage(self, mock_build_outputs, mock_perform_self_query_retrieval):
        # Query to test
        query = "chocolate cake recipe"

        # Setup mock return values
        mock_perform_self_query_retrieval.return_value = self.sample_recipe
        mock_build_outputs.return_value = [
            {
                "nutrition": self.mock_generation_output({
                    "text": "Nutrition info", "input_tokens": 12, "output_tokens": 30
                }),
                "shopping_list": self.mock_generation_output({
                    "text": "Shopping list", "input_tokens": 10, "output_tokens": 25
                }),
                "factoids": self.mock_generation_output({
                    "text": "Factoids", "input_tokens": 8, "output_tokens": 20
                }),
                "recipe": "Recipe content"
            }
        ]

        # Create and invoke the tool
        tool_function = create_recipes_self_query_tool()
        get_recipes_self_query = tool_function.invoke

        # Measure performance
        start_time = time.time()
        results_json_str = get_recipes_self_query(query)
        duration = time.time() - start_time
        results = json.loads(results_json_str)

        # Performance check
        self.assertLess(duration, 3.0, "Execution time exceeded 3 seconds")

        # Validate results + token counts
        total_input_tokens = 0
        total_output_tokens = 0

        for result in results:
            for key in ["nutrition", "shopping_list", "factoids"]:
                self.assertIn("text", result[key])
                self.assertIn("metadata", result[key])
                total_input_tokens += result[key]["metadata"].get("input_tokens", 0)
                total_output_tokens += result[key]["metadata"].get("output_tokens", 0)

            self.assertEqual(result["recipe"], self.sample_recipe[0]["page_content"])

        # Token usage limits (mock-based thresholds)
        self.assertLessEqual(total_input_tokens, 40, "Total input tokens exceeded threshold")
        self.assertLessEqual(total_output_tokens, 80, "Total output tokens exceeded threshold")

if __name__ == '__main__':
    unittest.main()
