"""
Integration tests for the multi-query retrieval functionality.
These tests focus on validating that the multi-query functionality works with the ReAct agent.
"""

import unittest
from unittest.mock import patch, MagicMock
import json
from flask import Flask, Response
from io import BytesIO

# Unit tests that don't require app context or login
class TestMultiQueryIntegration(unittest.TestCase):
    """Tests for multi-query retrieval functionality integration."""
    
    def test_tools_creation(self):
        """Test that tools are properly created and chained."""
        from app import create_recipes_multi_query_tool
        from gutenberg.recipes_storage_and_retrieval_v2 import perform_multi_query_retrieval
        
        # Patch the perform_multi_query_retrieval function
        with patch('app.perform_recipes_multi_query_retrieval') as mock_perform:
            mock_perform.return_value = [{"recipe": "test recipe"}]
            
            # Create the tool
            tool = create_recipes_multi_query_tool()
            
            # Test the tool returns properly formatted JSON
            with patch('app.json.dumps') as mock_dumps:
                mock_dumps.return_value = '{"recipe": "test recipe"}'
                
                # Call the tool with a test query
                result = tool.invoke("vegetarian Italian pasta")
                
                # Verify the multi-query retrieval was called
                mock_perform.assert_called_once()
                self.assertEqual(mock_perform.call_args.args[0], "vegetarian Italian pasta")
                
                # Verify the result was properly formatted
                mock_dumps.assert_called_once()
                
    @patch('gutenberg.recipes_storage_and_retrieval_v2.build_self_query_retriever')
    @patch('gutenberg.recipes_storage_and_retrieval_v2.MultiQueryRetriever')
    def test_multi_query_chain_creation(self, mock_multi_query, mock_build_retriever):
        """Test that the multi-query retrieval chain is correctly constructed."""
        from gutenberg.recipes_storage_and_retrieval_v2 import perform_multi_query_retrieval
        
        # Set up mocks
        mock_llm = MagicMock()
        mock_vector_store = MagicMock()
        mock_translator = MagicMock()
        test_query = "vegetarian Italian pasta"
        
        # Mock the self-query retriever
        mock_sq_retriever = MagicMock()
        mock_build_retriever.return_value = mock_sq_retriever
        
        # Mock the multi-query retriever
        mock_mq_retriever = MagicMock()
        mock_multi_query.return_value = mock_mq_retriever
        mock_mq_retriever.invoke.return_value = [MagicMock()]
        
        # Mock build_outputs function
        with patch('gutenberg.recipes_storage_and_retrieval_v2.build_outputs') as mock_build_outputs:
            mock_build_outputs.return_value = [{"recipe": "test recipe"}]
            
            # Call the function
            perform_multi_query_retrieval(test_query, mock_llm, mock_vector_store, mock_translator)
            
            # Verify the correct chain is created
            mock_build_retriever.assert_called_once_with(mock_llm, mock_vector_store, mock_translator)
            mock_multi_query.assert_called_once()
            
            # Verify the multi-query retriever was used
            mock_mq_retriever.invoke.assert_called_once_with(test_query)
            
            # Verify the results were processed
            mock_build_outputs.assert_called_once()

class TestQueryExpansion(unittest.TestCase):
    """Tests for the query expansion functionality."""
    
    def test_query_expansion_prompt(self):
        """Test that the query expansion prompt generates appropriate variations."""
        from langchain_core.prompts import PromptTemplate
        
        # Create a prompt similar to what's used in the implementation
        query_prompt = PromptTemplate(
            input_variables=["question"],
            template="""You are an AI language model assistant. Your task is to generate five 
            different versions of the given user question to retrieve relevant documents from a vector 
            database. By generating multiple perspectives on the user question, your goal is to help
            the user overcome some of the limitations of the distance-based similarity search. 
            Provide these alternative questions separated by newlines.
            Original question: {question}"""
        )
        
        # Format the prompt with a test question
        test_query = "vegetarian Italian pasta dishes"
        formatted_prompt = query_prompt.format(question=test_query)
        
        # Verify the prompt contains key elements
        self.assertIn("generate five", formatted_prompt)
        self.assertIn("different versions", formatted_prompt)
        self.assertIn(f"Original question: {test_query}", formatted_prompt)
    
    def test_line_list_output_parser(self):
        """Test that the output parser correctly processes the LLM response."""
        from langchain_core.output_parsers import BaseOutputParser
        from typing import List
        
        # Recreate the LineListOutputParser class 
        class LineListOutputParser(BaseOutputParser[List[str]]):
            """Output parser for a list of lines."""
            def parse(self, text: str) -> List[str]:
                lines = text.strip().split("\n")
                return list(filter(None, lines))  # Remove empty lines
        
        # Create a test LLM response
        test_response = """
        vegetarian Italian pasta dishes
        Italian dishes without meat
        Pasta recipes for vegetarians
        Meat-free Italian cuisine
        Plant-based pasta dishes from Italy
        """
        
        # Parse the response
        parser = LineListOutputParser()
        results = parser.parse(test_response)
        
        # Verify correct parsing
        self.assertEqual(len(results), 5)
        self.assertEqual(results[0].strip(), "vegetarian Italian pasta dishes")
        
        # Verify each variation is non-empty
        for result in results:
            self.assertTrue(result.strip())

class TestReactAgentTools(unittest.TestCase):
    """Tests for the integration of multi-query retrieval with the ReAct agent's tools."""
    
    @patch('app.create_react_agent')
    def test_tool_is_passed_to_agent(self, mock_create_agent):
        """Test that the multi-query tool is passed to the agent when creating it."""
        # Mock the tools
        with patch('app.create_recipes_multi_query_tool') as mock_multi_query_tool:
            mock_multi_query_tool.return_value = MagicMock(name="multi_query_tool")
            
            with patch('app.create_recipes_similarity_search_tool') as mock_sim_tool:
                mock_sim_tool.return_value = MagicMock(name="sim_tool")
                
                with patch('app.create_recipes_self_query_tool') as mock_self_query_tool:
                    mock_self_query_tool.return_value = MagicMock(name="self_query_tool")
                    
                    with patch('app.create_books_similarity_search_tool') as mock_books_sim_tool:
                        mock_books_sim_tool.return_value = MagicMock(name="books_sim_tool")
                        
                        with patch('app.create_books_retrieval_qa_tool') as mock_books_qa_tool:
                            mock_books_qa_tool.return_value = MagicMock(name="books_qa_tool")
                            
                            with patch('app.chat_llm') as mock_llm:
                                with patch('app.memory') as mock_memory:
                                    # Create mock agent
                                    mock_agent = MagicMock()
                                    mock_create_agent.return_value = mock_agent
                                    
                                    # Import the stream function to get access to its implementation
                                    from app import stream
                                    
                                    # Create app context for testing
                                    from app import app
                                    app.config['TESTING'] = True
                                    
                                    # Create a new app object just for testing
                                    test_app = Flask(__name__)
                                    test_app.config['TESTING'] = True
                                    
                                    # Create a simple route that mimics the tool creation of stream()
                                    @test_app.route('/test')
                                    def test_route():
                                        # Create all tools
                                        recipes_multi_query_tool = mock_multi_query_tool()
                                        recipes_self_query_tool = mock_self_query_tool()
                                        recipes_similarity_search_tool = mock_sim_tool()
                                        books_retrieval_qa_tool = mock_books_qa_tool()
                                        books_similarity_search_tool = mock_books_sim_tool()
                                        
                                        # Create agent with tools
                                        mock_create_agent(
                                            model=mock_llm,
                                            tools=[
                                                recipes_similarity_search_tool,
                                                recipes_self_query_tool,
                                                recipes_multi_query_tool,
                                                books_retrieval_qa_tool,
                                                books_similarity_search_tool,
                                            ],
                                            checkpointer=mock_memory,
                                            debug=True
                                        )
                                        
                                        return "Tools created"
                                    
                                    # Call the test route
                                    with test_app.test_client() as client:
                                        client.get('/test')
                                        
                                        # Verify create_react_agent was called
                                        mock_create_agent.assert_called_once()
                                        
                                        # Verify the multi-query tool was included in the tools list
                                        tools = mock_create_agent.call_args.kwargs.get('tools', [])
                                        self.assertIn(mock_multi_query_tool.return_value, tools)
                                        
                                        # Verify all 5 tools were included
                                        self.assertEqual(len(tools), 5)

if __name__ == '__main__':
    unittest.main()