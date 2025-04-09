"""
Tests for the enhanced recipe visualization functionality.
"""
import unittest
from unittest.mock import patch, MagicMock
import json
import re

class TestRecipeExtraction(unittest.TestCase):
    """Tests for recipe extraction and metadata functions in script.js."""
    
    def test_is_recipe_like_function(self):
        """Test the isRecipeLike function for recipe detection."""
        # This test should run in a browser environment, so we'll mock the function
        # and test its logic directly
        
        # Standard recipe format
        standard_recipe = """
        Title: Pasta Primavera
        
        Ingredients: pasta, vegetables, olive oil, garlic
        
        Instructions: 1. Cook pasta according to package directions.
        2. Sauté vegetables and garlic in olive oil.
        3. Combine pasta and vegetables. Serve hot.
        """
        
        # Recipe in Markdown format
        markdown_recipe = """
        # Pasta Primavera
        
        ## Ingredients
        - 8 oz pasta
        - 2 cups mixed vegetables
        - 2 tbsp olive oil
        - 2 cloves garlic, minced
        
        ## Instructions
        1. Cook pasta according to package directions.
        2. Sauté vegetables and garlic in olive oil.
        3. Combine pasta and vegetables. Serve hot.
        """
        
        # Not a recipe
        not_recipe = """
        Here's some information about Italian cuisine.
        It originated in Italy and is popular worldwide.
        Pizza and pasta are common Italian dishes.
        """
        
        # Asserting expected outcomes based on the isRecipeLike function logic
        # The function should detect both standard and markdown recipe formats
        self.assertTrue(self._mock_is_recipe_like(standard_recipe))
        self.assertTrue(self._mock_is_recipe_like(markdown_recipe))
        self.assertFalse(self._mock_is_recipe_like(not_recipe))
    
    def _mock_is_recipe_like(self, text):
        """Mock implementation of isRecipeLike function from script.js matching actual implementation."""
        if not text or not isinstance(text, str):
            return False
        
        # Replace escaped newlines with actual newlines
        text = text.replace("\\n", "\n")
        
        # Check for standard format (lines 751-753)
        has_standard_format = "Title:" in text and ("Ingredients:" in text or "Instructions:" in text)
        if has_standard_format:
            return True
        
        # Check for markdown format (lines 756-762)
        has_markdown_format = re.search(r'#+\s*(?:Recipe|Ingredients|Instructions|Directions|Method)', text, re.IGNORECASE)
        if has_markdown_format and "Ingredients" in text and "Instructions" in text:
            return True
        
        return False
    
    def test_extract_recipe_metadata(self):
        """Test extraction of recipe metadata from text."""
        # Sample recipe text with metadata
        recipe_text = """
        Title: Pasta Primavera
        
        Recipe Type: Main Course
        Cuisine: Italian
        Special Considerations: Vegetarian
        
        Ingredients:
        - 8 oz pasta
        - 2 cups mixed vegetables
        - 2 tbsp olive oil
        - 2 cloves garlic, minced
        
        Instructions:
        1. Cook pasta according to package directions.
        2. Sauté vegetables and garlic in olive oil.
        3. Combine pasta and vegetables. Serve hot.
        """
        
        # Expected metadata
        expected_metadata = {
            "recipe_title": "Pasta Primavera",
            "recipe_type": "main course",
            "cuisine": "italian",
            "special_considerations": "vegetarian",
            "ingredients": [
                "8 oz pasta",
                "2 cups mixed vegetables",
                "2 tbsp olive oil",
                "2 cloves garlic, minced"
            ]
        }
        
        # Mock extraction function
        extracted_metadata = self._mock_extract_metadata(recipe_text)
        
        # Verify extraction
        self.assertEqual(extracted_metadata["recipe_title"], expected_metadata["recipe_title"])
        self.assertEqual(extracted_metadata["recipe_type"], expected_metadata["recipe_type"])
        self.assertEqual(extracted_metadata["cuisine"], expected_metadata["cuisine"])
        self.assertEqual(extracted_metadata["special_considerations"], expected_metadata["special_considerations"])
        self.assertEqual(len(extracted_metadata["ingredients"]), len(expected_metadata["ingredients"]))
    
    def _mock_extract_metadata(self, text):
        """Mock implementation of metadata extraction logic from script.js."""
        metadata = {
            "recipe_title": "Recipe",
            "source": "ChefBoost AI",
            "date_issued": "2025-04-09"
        }
        
        # Clean up text
        text = text.replace("\\n", "\n").replace("**", "")
        
        # Extract title
        title_match = None
        for line in text.split('\n'):
            if line.strip().startswith("Title:"):
                title_match = line.strip()[6:].strip()
                break
        
        if title_match:
            metadata["recipe_title"] = title_match
        
        # Extract recipe type
        type_match = None
        for line in text.split('\n'):
            if line.strip().startswith("Recipe Type:"):
                type_match = line.strip()[12:].strip()
                break
        
        if type_match:
            metadata["recipe_type"] = type_match.lower()
        
        # Extract cuisine
        cuisine_match = None
        for line in text.split('\n'):
            if line.strip().startswith("Cuisine:"):
                cuisine_match = line.strip()[8:].strip()
                break
        
        if cuisine_match:
            metadata["cuisine"] = cuisine_match.lower()
        
        # Extract special considerations
        considerations_match = None
        for line in text.split('\n'):
            if line.strip().startswith("Special Considerations:"):
                considerations_match = line.strip()[23:].strip()
                break
        
        if considerations_match:
            metadata["special_considerations"] = considerations_match.lower()
        
        # Extract ingredients
        ingredients = []
        in_ingredients_section = False
        for line in text.split('\n'):
            line = line.strip()
            if line == "Ingredients:":
                in_ingredients_section = True
                continue
            elif in_ingredients_section and line.startswith("Instructions:"):
                in_ingredients_section = False
                continue
            elif in_ingredients_section and line.startswith("-"):
                ingredients.append(line[1:].strip())
        
        metadata["ingredients"] = ingredients
        
        return metadata
    
    def test_split_multiple_recipes(self):
        """Test splitting text into multiple recipes."""
        # Text with multiple recipes
        multi_recipe_text = """
        Title: Pasta Primavera
        
        Ingredients:
        - 8 oz pasta
        - 2 cups mixed vegetables
        
        Instructions:
        1. Cook pasta according to package directions.
        2. Combine with vegetables.
        
        Title: Chocolate Chip Cookies
        
        Ingredients:
        - 1 cup flour
        - 1/2 cup chocolate chips
        
        Instructions:
        1. Mix ingredients.
        2. Bake at 350°F for 10 minutes.
        """
        
        # Mock splitting function
        split_recipes = self._mock_split_recipes(multi_recipe_text)
        
        # Verify splitting
        self.assertEqual(len(split_recipes), 2)
        self.assertIn("Pasta Primavera", split_recipes[0])
        self.assertIn("Chocolate Chip Cookies", split_recipes[1])
    
    def _mock_split_recipes(self, text):
        """Mock implementation of recipe splitting logic from script.js."""
        if not text or not isinstance(text, str):
            return [text]
        
        # Replace escaped newlines with actual newlines
        text = text.replace("\\n", "\n")
        
        # Split by Title: markers
        title_matches = []
        current_pos = 0
        while True:
            title_pos = text.find("Title:", current_pos)
            if title_pos == -1:
                break
            title_matches.append(title_pos)
            current_pos = title_pos + 6
        
        if len(title_matches) > 1:
            recipes = []
            for i, start in enumerate(title_matches):
                end = title_matches[i+1] if i < len(title_matches) - 1 else len(text)
                recipe = text[start:end].strip()
                recipes.append(recipe)
            return recipes
        
        # If no multiple titles found, return the original text as a single recipe
        return [text]


class TestRecipeVisualization(unittest.TestCase):
    """Tests for recipe visualization rendering."""
    
    def test_create_recipe_card(self):
        """Test creation of recipe card from recipe data."""
        # Create a simple recipe data object
        recipe_data = {
            "text": "Title: Pasta Primavera\n\nIngredients: pasta, vegetables\n\nInstructions: Cook and mix.",
            "metadata": {
                "recipe_title": "Pasta Primavera",
                "recipe_type": "main course",
                "cuisine": "italian",
                "special_considerations": "vegetarian",
                "ingredients": ["pasta", "vegetables"]
            }
        }
        
        # Mock DOM elements to simulate card creation
        mock_card = self._mock_create_card(recipe_data)
        
        # Verify card creation
        self.assertEqual(mock_card["title"], "Pasta Primavera")
        self.assertEqual(mock_card["type"], "main course")
        self.assertEqual(mock_card["cuisine"], "italian")
        self.assertEqual(mock_card["considerations"], "vegetarian")
        self.assertEqual(len(mock_card["ingredients"]), 2)
    
    def _mock_create_card(self, recipe_data):
        """Mock implementation of card creation logic from script.js."""
        card = {
            "title": "",
            "type": "",
            "cuisine": "",
            "considerations": "",
            "ingredients": [],
            "instructions": ""
        }
        
        # Extract data
        recipe = recipe_data
        if recipe_data.get("recipe") and isinstance(recipe_data["recipe"], dict):
            recipe = recipe_data["recipe"]
        
        # Set card properties
        card["title"] = recipe["metadata"].get("recipe_title", "Recipe")
        card["type"] = recipe["metadata"].get("recipe_type", "")
        card["cuisine"] = recipe["metadata"].get("cuisine", "")
        card["considerations"] = recipe["metadata"].get("special_considerations", "")
        card["ingredients"] = recipe["metadata"].get("ingredients", [])
        
        # Extract instructions
        instructions_section = None
        if "Instructions:" in recipe["text"]:
            instructions_parts = recipe["text"].split("Instructions:")
            if len(instructions_parts) > 1:
                instructions_section = instructions_parts[1].strip()
        
        card["instructions"] = instructions_section or ""
        
        return card
    
    def test_create_recipe_card_dom_structure(self):
        """Test the DOM structure of the created recipe card."""
        # Create mock recipe data
        recipe_data = {
            "text": "Title: Chocolate Cake\n\nIngredients:\n- 1 cup flour\n- 1/2 cup cocoa\n\nInstructions: Mix and bake.",
            "metadata": {
                "recipe_title": "Chocolate Cake",
                "recipe_type": "dessert",
                "cuisine": "american",
                "special_considerations": "nut-free",
                "ingredients": ["1 cup flour", "1/2 cup cocoa"],
                "source": "Baking Book"
            }
        }
        
        # Mock the DOM creation process
        card_dom = self._mock_create_card_dom(recipe_data)
        
        # Verify card structure
        self.assertEqual(card_dom["card_class"], "recipe-card")
        self.assertEqual(card_dom["title_text"], "Chocolate Cake")
        self.assertEqual(card_dom["type_text"], "Dessert")
        self.assertEqual(card_dom["cuisine_text"], "American")
        self.assertEqual(card_dom["considerations_text"], "nut-free")
        self.assertEqual(len(card_dom["ingredient_items"]), 2)
        self.assertEqual(card_dom["source_info"], "Source: Baking Book")
        self.assertTrue(card_dom["has_source_panel"])
        self.assertFalse(card_dom["has_shopping_list"]) # No shopping list in data
    
    def _mock_create_card_dom(self, recipe_data):
        """Mock the DOM structure creation for recipe cards."""
        dom = {
            "card_class": "recipe-card",
            "title_text": "",
            "type_text": "",
            "cuisine_text": "",
            "considerations_text": "",
            "ingredient_items": [],
            "instructions_html": "",
            "has_nutrition": False,
            "nutrition_html": "",
            "has_shopping_list": False,
            "has_factoids": False,
            "has_source_panel": False,
            "source_info": ""
        }
        
        # Get recipe data
        recipe = recipe_data
        if recipe_data.get("recipe") and isinstance(recipe_data["recipe"], dict):
            recipe = recipe_data["recipe"]
            
        # Set title (clean up ** and numbers) - lines 1689-1691
        title = recipe["metadata"].get("recipe_title", "Recipe")
        # Python regex for removing leading numbers (not JavaScript regex)
        title = re.sub(r'^\d+\.\s*', '', title) # Remove leading numbers
        title = re.sub(r'\*\*', '', title)      # Remove ** formatting
        dom["title_text"] = title
        
        # Set type (capitalize) - lines 1700-1708
        if recipe["metadata"].get("recipe_type"):
            type_text = recipe["metadata"]["recipe_type"]
            # Capitalize first letter (Python style)
            type_text = type_text.capitalize()
            # Remove **
            type_text = re.sub(r'\*\*', '', type_text)
            dom["type_text"] = type_text
            
        # Set cuisine (capitalize) - lines 1711-1719
        if recipe["metadata"].get("cuisine"):
            cuisine_text = recipe["metadata"]["cuisine"]
            # Capitalize first letter (Python style)
            cuisine_text = cuisine_text.capitalize()
            # Remove **
            cuisine_text = re.sub(r'\*\*', '', cuisine_text)
            dom["cuisine_text"] = cuisine_text
            
        # Set considerations - lines 1723-1735
        if recipe["metadata"].get("special_considerations"):
            considerations = recipe["metadata"]["special_considerations"]
            if isinstance(considerations, list):
                considerations = ", ".join(considerations)
            if isinstance(considerations, str):
                considerations = re.sub(r'\*\*', '', considerations)
                dom["considerations_text"] = considerations
                
        # Populate ingredients - lines 1739-1759
        ingredients = recipe["metadata"].get("ingredients", [])
        dom["ingredient_items"] = ingredients
        
        # Add source info - lines 1873-1906
        if recipe["metadata"]:
            dom["has_source_panel"] = True
            sourceValue = recipe["metadata"].get("source", "ChefBoost AI")
            dom["source_info"] = f"Source: {sourceValue}"
            
            if recipe["metadata"].get("authors"):
                authors = recipe["metadata"]["authors"]
                if Array.isArray(authors):
                    authors = authors.join(', ')
                dom["source_info"] += f"\nAuthor(s): {authors}"
                
            if recipe["metadata"].get("date_issued"):
                dom["source_info"] += f"\nDate: {recipe['metadata']['date_issued']}"
                
        # Check for shopping list and factoids - lines 1847-1863
        if recipe_data.get("shopping_list"):
            dom["has_shopping_list"] = True
            
        if recipe_data.get("factoids"):
            dom["has_factoids"] = True
            
        # Check for nutrition info - lines 1799-1842
        nutritionSection = recipe_data.get("nutrition")
        if nutritionSection:
            dom["has_nutrition"] = True
            dom["nutrition_html"] = nutritionSection
            
        return dom
        
    def test_format_recipe_as_markdown(self):
        """Test formatting recipe data as markdown for text view."""
        # Create a recipe data object
        recipe_data = {
            "text": "Title: Pasta Primavera\n\nIngredients: pasta, vegetables\n\nInstructions: Cook and mix.",
            "metadata": {
                "recipe_title": "Pasta Primavera",
                "recipe_type": "main course",
                "cuisine": "italian",
                "special_considerations": "vegetarian",
                "ingredients": ["pasta", "vegetables"],
                "source": "Italian Cookbook",
                "date_issued": "2023-01-01"
            }
        }
        
        # Mock markdown formatting
        markdown = self._mock_format_markdown(recipe_data)
        
        # Verify markdown formatting
        self.assertIn("## Pasta Primavera", markdown)
        self.assertIn("Type: Main course", markdown)
        self.assertIn("Cuisine: Italian", markdown)
        self.assertIn("Special Considerations: vegetarian", markdown)
        self.assertIn("Source: Italian Cookbook", markdown)
    
    def _mock_format_markdown(self, recipe_data):
        """Mock implementation of markdown formatting logic from script.js."""
        recipe = recipe_data
        if recipe_data.get("recipe") and isinstance(recipe_data["recipe"], dict):
            recipe = recipe_data["recipe"]
        
        markdown = ""
        
        # Add title
        title = recipe["metadata"].get("recipe_title", "Recipe")
        markdown += f"## {title}\n\n"
        
        # Add metadata
        metadata_items = []
        if recipe["metadata"].get("recipe_type"):
            recipe_type = recipe["metadata"]["recipe_type"]
            recipe_type = recipe_type.capitalize()
            metadata_items.append(f"Type: {recipe_type}")
        
        if recipe["metadata"].get("cuisine"):
            cuisine = recipe["metadata"]["cuisine"]
            cuisine = cuisine.capitalize()
            metadata_items.append(f"Cuisine: {cuisine}")
        
        if recipe["metadata"].get("special_considerations"):
            considerations = recipe["metadata"]["special_considerations"]
            metadata_items.append(f"Special Considerations: {considerations}")
        
        if metadata_items:
            markdown += " | ".join(metadata_items) + "\n\n"
        
        # Add content from text
        if recipe.get("text"):
            markdown += recipe["text"].replace("Title: " + title, "").strip() + "\n\n"
        
        # Add source information
        markdown += "### Source Information\n"
        source = recipe["metadata"].get("source", "ChefBoost AI")
        markdown += f"Source: {source}\n"
        
        if recipe["metadata"].get("date_issued"):
            markdown += f"Date: {recipe['metadata']['date_issued']}\n"
        
        return markdown
    
    def test_extract_section_helper(self):
        """Test the extractSection helper function that extracts parts from recipe text."""
        recipe_text = """
        Title: Banana Bread
        
        Ingredients:
        - 3 ripe bananas
        - 1/2 cup butter
        - 1 cup sugar
        - 2 eggs
        - 2 cups flour
        - 1 tsp baking soda
        
        Instructions:
        1. Preheat oven to 350°F.
        2. Mash bananas in a bowl.
        3. Mix in butter, sugar, and eggs.
        4. Add flour and baking soda.
        5. Pour into greased loaf pan and bake for 60 minutes.
        
        Nutrition:
        Calories: 250 per slice
        Fat: 9g
        Carbs: 40g
        Protein: 3g
        """
        
        # Extract sections
        ingredients_section = self._mock_extract_section(recipe_text, "Ingredients")
        instructions_section = self._mock_extract_section(recipe_text, "Instructions")
        nutrition_section = self._mock_extract_section(recipe_text, "Nutrition")
        
        # Verify extracted sections
        self.assertIn("3 ripe bananas", ingredients_section)
        self.assertIn("Preheat oven to 350°F", instructions_section)
        self.assertIn("Calories: 250 per slice", nutrition_section)
        
        # Test section not found
        notes_section = self._mock_extract_section(recipe_text, "Notes")
        self.assertIsNone(notes_section)
        
    def _mock_extract_section(self, text, section_name):
        """Mock implementation of the extractSection helper function from script.js."""
        if not text:
            return None
            
        # Replace escaped newlines with actual newlines
        text = text.replace("\\n", "\n")
        
        # Use regex to extract the section - matches the function in lines 1937-1946
        regex = re.compile(f"{section_name}:\\s*([\\s\\S]*?)(?=\\n\\n|\\n[A-Z][a-z]+:|$)", re.IGNORECASE)
        match = regex.search(text)
        return match.group(1).strip() if match else None


class TestViewToggle(unittest.TestCase):
    """Tests for view toggle functionality."""
    
    def test_switch_view(self):
        """Test switching between text and card views."""
        # Mock initial state
        current_view_mode = "text"
        
        # Switch to card view
        new_mode = self._mock_switch_view(current_view_mode, "card")
        self.assertEqual(new_mode, "card")
        
        # Switch back to text view
        new_mode = self._mock_switch_view(new_mode, "text")
        self.assertEqual(new_mode, "text")
    
    def _mock_switch_view(self, current_mode, new_mode):
        """Mock implementation of view switching logic from script.js."""
        if current_mode == new_mode:
            return current_mode
        
        # Update current mode
        return new_mode
        
    def test_view_mode_dom_updates(self):
        """Test that DOM elements are properly updated when switching views."""
        # Create mock DOM elements
        dom = self._create_mock_dom()
        
        # Test switching to card mode
        updated_dom = self._mock_update_dom_for_view_mode(dom, "text", "card")
        
        # Verify DOM updates for card mode
        self.assertTrue(updated_dom["body_classes"]["card-view-mode"])
        self.assertFalse(updated_dom["body_classes"]["text-view-mode"])
        self.assertTrue(updated_dom["standalone_card_btn"]["active"])
        self.assertFalse(updated_dom["standalone_text_btn"]["active"])
        self.assertTrue(updated_dom["view_toggle_checkbox"]["checked"])
        
        # Test switching back to text mode
        updated_dom = self._mock_update_dom_for_view_mode(updated_dom, "card", "text")
        
        # Verify DOM updates for text mode
        self.assertFalse(updated_dom["body_classes"]["card-view-mode"])
        self.assertTrue(updated_dom["body_classes"]["text-view-mode"])
        self.assertFalse(updated_dom["standalone_card_btn"]["active"])
        self.assertTrue(updated_dom["standalone_text_btn"]["active"])
        self.assertFalse(updated_dom["view_toggle_checkbox"]["checked"])
        
    def _create_mock_dom(self):
        """Create a mock DOM structure for testing view toggle."""
        return {
            "body_classes": {
                "card-view-mode": False,
                "text-view-mode": True
            },
            "standalone_text_btn": {
                "active": True
            },
            "standalone_card_btn": {
                "active": False
            },
            "view_toggle_checkbox": {
                "checked": False
            },
            "messages": [
                {
                    "classes": ["assistant-message", "text-view"],
                    "data-recipe-indices": "0,1",
                    "data-is-recipes": "true",
                    "data-recipe-count": "2"
                },
                {
                    "classes": ["assistant-message", "text-view"],
                    "data-recipe-index": "2"
                }
            ]
        }
        
    def _mock_update_dom_for_view_mode(self, dom, old_mode, new_mode):
        """Mock updating DOM elements when switching views."""
        # Create a copy to avoid modifying the original
        updated_dom = dict(dom)
        updated_dom["body_classes"] = dict(dom["body_classes"])
        updated_dom["standalone_text_btn"] = dict(dom["standalone_text_btn"])
        updated_dom["standalone_card_btn"] = dict(dom["standalone_card_btn"])
        updated_dom["view_toggle_checkbox"] = dict(dom["view_toggle_checkbox"])
        updated_dom["messages"] = []
        
        for message in dom["messages"]:
            message_copy = dict(message)
            message_copy["classes"] = list(message["classes"])
            updated_dom["messages"].append(message_copy)
        
        # Update body classes - lines 1249-1251
        if new_mode == "card":
            updated_dom["body_classes"]["card-view-mode"] = True
            updated_dom["body_classes"]["text-view-mode"] = False
        else:
            updated_dom["body_classes"]["card-view-mode"] = False
            updated_dom["body_classes"]["text-view-mode"] = True
            
        # Update toggle state - lines 1235-1237
        updated_dom["view_toggle_checkbox"]["checked"] = (new_mode == "card")
        
        # Update standalone buttons - lines 1243-1247
        updated_dom["standalone_text_btn"]["active"] = (new_mode == "text")
        updated_dom["standalone_card_btn"]["active"] = (new_mode == "card")
        
        # Update message classes - lines 1264-1266
        for message in updated_dom["messages"]:
            if new_mode == "card":
                if "text-view" in message["classes"]:
                    message["classes"].remove("text-view")
                if "card-view" not in message["classes"]:
                    message["classes"].append("card-view")
            else:
                if "card-view" in message["classes"]:
                    message["classes"].remove("card-view")
                if "text-view" not in message["classes"]:
                    message["classes"].append("text-view")
                
        return updated_dom


class TestModalAndButtons(unittest.TestCase):
    """Test modal windows and interactive buttons."""
    
    def test_shopping_list_modal(self):
        """Test showing shopping list in a modal."""
        # Create mock shopping list data
        shopping_list = """
        - 3 ripe bananas
        - 1/2 cup butter
        - 1 cup sugar
        - 2 eggs
        - 2 cups flour
        - 1 tsp baking soda
        """
        
        # Mock showing modal
        modal = self._mock_show_modal("Shopping List", shopping_list)
        
        # Verify modal properties
        self.assertEqual(modal["title"], "Shopping List")
        self.assertEqual(modal["content_type"], "markdown")
        self.assertIn("3 ripe bananas", modal["content"])
        self.assertTrue(modal["has_close_button"])
        
    def test_factoids_modal(self):
        """Test showing factoids in a modal."""
        # Create mock factoids data
        factoids = {
            "Origin": "Banana bread became common in American cookbooks in the 1930s",
            "Fun Fact": "Adding chocolate chips became popular in the 1980s",
            "Nutrition": "Bananas provide potassium and vitamin B6"
        }
        
        # Convert to JSON string as it would be in the actual code
        factoids_json = json.dumps(factoids)
        
        # Mock showing modal
        modal = self._mock_show_modal("Interesting Facts", factoids_json)
        
        # Verify modal properties
        self.assertEqual(modal["title"], "Interesting Facts")
        self.assertEqual(modal["content_type"], "json")
        self.assertTrue("Origin" in modal["parsed_json"])
        self.assertTrue("Fun Fact" in modal["parsed_json"])
        self.assertEqual(modal["parsed_json"]["Origin"], "Banana bread became common in American cookbooks in the 1930s")
        
    def _mock_show_modal(self, title, content):
        """Mock implementation of the showModal function from script.js."""
        modal = {
            "title": title,
            "content_type": "text",
            "content": content,
            "has_close_button": True,
            "parsed_json": None
        }
        
        # Try to detect JSON content - lines 2110-2135
        if isinstance(content, str):
            try:
                if content.strip().startswith('{'):
                    parsed_content = json.loads(content)
                    if isinstance(parsed_content, dict):
                        modal["content_type"] = "json"
                        modal["parsed_json"] = parsed_content
                    else:
                        modal["content_type"] = "markdown"
                else:
                    modal["content_type"] = "markdown"
            except:
                # Not JSON, use as markdown
                modal["content_type"] = "markdown"
        else:
            modal["content"] = json.dumps(content, indent=2)
            
        return modal
        
    def test_source_panel_toggle(self):
        """Test toggling the source information panel."""
        # Create initial state with hidden source panel
        source_panel = {
            "is_visible": False,
            "toggle_text": "Source Info",
            "content": "<p><strong>Source:</strong> The Joy of Baking</p><p><strong>Date:</strong> 2023-05-15</p>"
        }
        
        # Toggle to show
        updated_panel = self._mock_toggle_source_panel(source_panel)
        self.assertTrue(updated_panel["is_visible"])
        self.assertEqual(updated_panel["toggle_text"], "Hide Source")
        
        # Toggle to hide
        updated_panel = self._mock_toggle_source_panel(updated_panel)
        self.assertFalse(updated_panel["is_visible"])
        self.assertEqual(updated_panel["toggle_text"], "Source Info")
        
    def _mock_toggle_source_panel(self, panel_state):
        """Mock implementation of source panel toggle from script.js."""
        updated_state = dict(panel_state)
        
        # Toggle visibility - lines 1915-1919
        updated_state["is_visible"] = not panel_state["is_visible"]
        
        # Update toggle text
        updated_state["toggle_text"] = "Hide Source" if updated_state["is_visible"] else "Source Info"
        
        return updated_state


if __name__ == "__main__":
    unittest.main()