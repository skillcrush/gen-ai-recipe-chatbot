import unittest
from unittest.mock import patch
import json

# Import the tool and the build_outputs reference
from app import create_recipes_self_query_tool
from gutenberg.recipes_storage_and_retrieval_v2 import build_outputs


class TestReActAgentIntegration(unittest.TestCase):
    def setUp(self):
        # Sample recipe returned by the mocked perform_self_query_retrieval
        self.sample_recipe = [
            {
                "page_content": "This is a chocolate cake recipe.",
                "metadata": {
                    "recipe_name": "Chocolate Cake",
                    "ingredients": ["chocolate", "flour", "sugar"],
                    "cook_time": "45 minutes"
                }
            }
        ]

        # Simulated outputs from build_outputs
        self.augmented_output = [
            {
                "nutrition": {"text": "Approx. 500 calories"},
                "shopping_list": {"text": "chocolate, flour, sugar"},
                "factoids": {"text": "Chocolate was once used as currency"},
                "recipe": "This is a chocolate cake recipe."
            }
        ]

    @patch("gutenberg.recipes_storage_and_retrieval_v2.perform_self_query_retrieval")
    @patch("gutenberg.recipes_storage_and_retrieval_v2.build_outputs")
    def test_react_agent_returns_augmented_recipe(self, mock_build_outputs, mock_retrieve):
        query = "chocolate cake recipe"

        # Mock behaviors
        mock_retrieve.return_value = self.sample_recipe
        mock_build_outputs.return_value = self.augmented_output

        # Create the tool and invoke the agent
        tool_function = create_recipes_self_query_tool()
        results_json = tool_function.invoke(query)
        results = json.loads(results_json)

        # Check that results have expected keys and values
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)

        result = results[0]
        self.assertIn("nutrition", result)
        self.assertIn("shopping_list", result)
        self.assertIn("factoids", result)
        self.assertIn("recipe", result)

        self.assertEqual(result["nutrition"]["text"], "Approx. 500 calories")
        self.assertEqual(result["shopping_list"]["text"], "chocolate, flour, sugar")
        self.assertEqual(result["factoids"]["text"], "Chocolate was once used as currency")
        self.assertEqual(result["recipe"], "This is a chocolate cake recipe.")


if __name__ == "__main__":
    unittest.main()
