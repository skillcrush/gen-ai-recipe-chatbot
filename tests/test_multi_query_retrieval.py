import unittest
from unittest.mock import patch, MagicMock
import json
from typing import List
from langchain_core.output_parsers import BaseOutputParser

# Import the implementation being tested
from gutenberg.recipes_storage_and_retrieval_v2 import (
    perform_multi_query_retrieval,
    build_self_query_retriever,
    build_outputs
)

class TestMultiQueryRetrieval(unittest.TestCase):
    """Test cases for the multi-query retrieval functionality."""

    def setUp(self):
        # Setup common test fixtures
        self.mock_llm = MagicMock()
        self.mock_vector_store = MagicMock()
        self.mock_translator = MagicMock()
        self.test_query = "vegetarian Italian pasta dishes"

    @patch('gutenberg.recipes_storage_and_retrieval_v2.MultiQueryRetriever')
    @patch('gutenberg.recipes_storage_and_retrieval_v2.build_self_query_retriever')
    def test_perform_multi_query_retrieval_chain(self, mock_build_retriever, mock_multi_query):
        """Test that multi-query retrieval creates the proper chain of components."""
        # Set up mocks
        mock_sq_retriever = MagicMock()
        mock_build_retriever.return_value = mock_sq_retriever
        
        mock_mq_retriever = MagicMock()
        mock_multi_query.return_value = mock_mq_retriever
        mock_mq_retriever.invoke.return_value = [MagicMock()]
        
        # Mock the build_outputs function
        with patch('gutenberg.recipes_storage_and_retrieval_v2.build_outputs') as mock_build_outputs:
            mock_build_outputs.return_value = [{"recipe": "test recipe"}]
            
            # Call the function under test
            perform_multi_query_retrieval(self.test_query, self.mock_llm, self.mock_vector_store, self.mock_translator)
            
            # Verify the correct chain is created
            mock_build_retriever.assert_called_once_with(self.mock_llm, self.mock_vector_store, self.mock_translator)
            mock_multi_query.assert_called_once()
            
            # Verify the retriever was invoked with the query
            mock_mq_retriever.invoke.assert_called_once_with(self.test_query)

    @patch('gutenberg.recipes_storage_and_retrieval_v2.build_outputs')
    @patch('gutenberg.recipes_storage_and_retrieval_v2.MultiQueryRetriever')
    @patch('gutenberg.recipes_storage_and_retrieval_v2.build_self_query_retriever')
    def test_perform_multi_query_returns_processed_results(self, mock_build_retriever, mock_multi_query, mock_build_outputs):
        """Test that multi-query retrieval returns processed results."""
        # Set up mocks
        mock_sq_retriever = MagicMock()
        mock_build_retriever.return_value = mock_sq_retriever
        
        mock_mq_retriever = MagicMock()
        mock_multi_query.return_value = mock_mq_retriever
        
        mock_results = [MagicMock(), MagicMock()]
        mock_mq_retriever.invoke.return_value = mock_results
        
        mock_processed_results = [{"recipe": "processed"}]
        mock_build_outputs.return_value = mock_processed_results
        
        # Call the function under test
        result = perform_multi_query_retrieval(self.test_query, self.mock_llm, self.mock_vector_store, self.mock_translator)
        
        # Verify the results were processed correctly
        mock_build_outputs.assert_called_once_with(mock_results, self.mock_llm)
        self.assertEqual(result, mock_processed_results)

    def test_line_list_output_parser(self):
        """Test that a LineListOutputParser would correctly parse multiple lines."""
        # Recreate the LineListOutputParser as it's defined locally in perform_multi_query_retrieval
        class LineListOutputParser(BaseOutputParser[List[str]]):
            """Output parser for a list of lines."""
            def parse(self, text: str) -> List[str]:
                lines = text.strip().split("\n")
                return list(filter(None, lines))  # Remove empty lines
        
        parser = LineListOutputParser()
        
        # Test parsing multiple lines
        test_input = """
        vegetarian Italian pasta with tomatoes
        classic Italian pasta dishes without meat
        simple pasta recipes with vegetables
        meat-free Italian cuisine
        vegetable pasta dishes from Italy
        """
        
        result = parser.parse(test_input)
        
        # Verify we get 5 non-empty lines
        self.assertEqual(len(result), 5)
        for line in result:
            self.assertTrue(line.strip())

    @patch('langchain.retrievers.self_query.base.SelfQueryRetriever')
    @patch('langchain.chains.query_constructor.base.StructuredQueryOutputParser')
    @patch('langchain.chains.query_constructor.base.get_query_constructor_prompt')
    def test_build_self_query_retriever_mock(self, mock_get_prompt, mock_output_parser, mock_self_query_retriever):
        """Test that self-query retriever is correctly built with metadata fields."""
        # Create mocks for the dependencies
        mock_llm = MagicMock()
        mock_vector_store = MagicMock()
        mock_translator = MagicMock()
        
        # Mock the output parser
        mock_parser = MagicMock()
        mock_output_parser.from_components.return_value = mock_parser
        
        # Mock the prompt template
        mock_prompt = MagicMock()
        mock_get_prompt.return_value = mock_prompt
        
        # Call the function
        with patch('gutenberg.recipes_storage_and_retrieval_v2.get_query_constructor_prompt', mock_get_prompt):
            with patch('gutenberg.recipes_storage_and_retrieval_v2.StructuredQueryOutputParser', mock_output_parser):
                # Only mock the constructor, not the entire class
                with patch('gutenberg.recipes_storage_and_retrieval_v2.SelfQueryRetriever') as mock_sq:
                    mock_sq.return_value = MagicMock()
                    
                    result = build_self_query_retriever(mock_llm, mock_vector_store, mock_translator)
                    
                    # Verify SelfQueryRetriever was instantiated
                    mock_sq.assert_called_once()
                    
                    # Verify it was called with correct parameters
                    call_kwargs = mock_sq.call_args.kwargs
                    self.assertEqual(call_kwargs['vectorstore'], mock_vector_store)
                    self.assertEqual(call_kwargs['structured_query_translator'], mock_translator)

class TestMultiQueryReactAgentIntegration(unittest.TestCase):
    """Tests for the integration of multi-query retrieval with the ReAct agent."""
    
    @patch('app.perform_recipes_multi_query_retrieval')
    def test_multi_query_tool_creation(self, mock_perform_retrieval):
        """Test that the multi-query tool is correctly created and returns JSON results."""
        from app import create_recipes_multi_query_tool
        
        # Setup
        mock_perform_retrieval.return_value = [{"recipe": "test recipe"}]
        
        # Get the tool function
        multi_query_tool = create_recipes_multi_query_tool()
        
        # Call the tool function's invoke method instead of calling directly
        result = multi_query_tool.invoke("test query")
        
        # Verify the result is properly formatted JSON
        result_dict = json.loads(result)
        self.assertEqual(result_dict, [{"recipe": "test recipe"}])
        
        # Verify the retrieval function was called with the right parameters
        mock_perform_retrieval.assert_called_once()
        args = mock_perform_retrieval.call_args.args
        self.assertEqual(args[0], "test query")  # First arg should be the query

class TestMultiQueryPrompts(unittest.TestCase):
    """Tests for the prompt templates used in multi-query retrieval."""
    
    def test_query_expansion_prompt(self):
        """Test that the query expansion prompt generates appropriate variations."""
        # Create a prompt similar to the one used in the implementation
        from langchain_core.prompts import PromptTemplate
        
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
        formatted_prompt = query_prompt.format(question="vegetarian Italian pasta dishes")
        
        # Check the prompt contains the key elements
        self.assertIn("generate five", formatted_prompt)
        self.assertIn("different versions", formatted_prompt)
        self.assertIn("Original question: vegetarian Italian pasta dishes", formatted_prompt)

if __name__ == '__main__':
    unittest.main()