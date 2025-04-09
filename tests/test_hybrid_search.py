import unittest
from unittest.mock import patch, MagicMock
import json

# Import the implementation to be tested
from gutenberg.recipes_storage_and_retrieval_v2 import (
    perform_similarity_search,
    perform_self_query_retrieval,
    perform_multi_query_retrieval
)

class TestHybridSearch(unittest.TestCase):
    """Test suite for hybrid search techniques combining different retrieval methods."""
    
    def setUp(self):
        # Common test fixtures
        self.mock_llm = MagicMock()
        self.mock_vector_store = MagicMock()
        self.mock_translator = MagicMock()
        self.test_query = "Find dessert recipes that combine french and italian cooking"
    
    @patch('gutenberg.recipes_storage_and_retrieval_v2.build_outputs')
    def test_similarity_search_retrieval(self, mock_build_outputs):
        """Test that similarity search retrieval works as expected."""
        # Setup
        mock_docs = [MagicMock(), MagicMock()]
        self.mock_vector_store.similarity_search.return_value = mock_docs
        mock_build_outputs.return_value = [{"recipe": "test recipe"}]
        
        # Call the function under test
        result = perform_similarity_search(self.test_query, self.mock_llm, self.mock_vector_store)
        
        # Verify the vector store was queried correctly
        self.mock_vector_store.similarity_search.assert_called_once_with(self.test_query)
        
        # Verify results were processed
        mock_build_outputs.assert_called_once_with(mock_docs, self.mock_llm)
        self.assertEqual(result, [{"recipe": "test recipe"}])
    
    @patch('gutenberg.recipes_storage_and_retrieval_v2.build_self_query_retriever')
    @patch('gutenberg.recipes_storage_and_retrieval_v2.build_outputs')
    def test_self_query_retrieval(self, mock_build_outputs, mock_build_retriever):
        """Test that self-query retrieval properly uses metadata filtering."""
        # Setup
        mock_retriever = MagicMock()
        mock_build_retriever.return_value = mock_retriever
        mock_docs = [MagicMock(), MagicMock()]
        mock_retriever.invoke.return_value = mock_docs
        mock_build_outputs.return_value = [{"recipe": "filtered recipe"}]
        
        # Call the function under test
        result = perform_self_query_retrieval(self.test_query, self.mock_llm, self.mock_vector_store, self.mock_translator)
        
        # Verify retriever was built and used correctly
        mock_build_retriever.assert_called_once_with(self.mock_llm, self.mock_vector_store, self.mock_translator)
        mock_retriever.invoke.assert_called_once_with(self.test_query)
        
        # Verify results were processed
        mock_build_outputs.assert_called_once_with(mock_docs, self.mock_llm)
        self.assertEqual(result, [{"recipe": "filtered recipe"}])
    
    @patch('gutenberg.recipes_storage_and_retrieval_v2.build_self_query_retriever')
    @patch('gutenberg.recipes_storage_and_retrieval_v2.MultiQueryRetriever')
    @patch('gutenberg.recipes_storage_and_retrieval_v2.build_outputs')
    def test_multi_query_retrieval(self, mock_build_outputs, mock_multi_query, mock_build_retriever):
        """Test that multi-query retrieval combines self-query with query expansion."""
        # Setup
        mock_sq_retriever = MagicMock()
        mock_build_retriever.return_value = mock_sq_retriever
        
        mock_multi_retriever = MagicMock()
        mock_multi_query.return_value = mock_multi_retriever
        mock_docs = [MagicMock(), MagicMock()]
        mock_multi_retriever.invoke.return_value = mock_docs
        
        mock_build_outputs.return_value = [{"recipe": "expanded query result"}]
        
        # Call the function under test
        result = perform_multi_query_retrieval(self.test_query, self.mock_llm, self.mock_vector_store, self.mock_translator)
        
        # Verify self-query retriever was built
        mock_build_retriever.assert_called_once_with(self.mock_llm, self.mock_vector_store, self.mock_translator)
        
        # Verify multi-query retriever was created with self-query retriever
        mock_multi_query.assert_called_once()
        kwargs = mock_multi_query.call_args.kwargs
        self.assertEqual(kwargs['retriever'], mock_sq_retriever)
        
        # Verify multi-query retriever was invoked with the query
        mock_multi_retriever.invoke.assert_called_once_with(self.test_query)
        
        # Verify results were processed
        mock_build_outputs.assert_called_once_with(mock_docs, self.mock_llm)
        self.assertEqual(result, [{"recipe": "expanded query result"}])

class TestComparativeRetrieval(unittest.TestCase):
    """Test suite for comparing the different retrieval methods."""
    
    def setUp(self):
        self.mock_llm = MagicMock()
        self.mock_vector_store = MagicMock()
        self.mock_translator = MagicMock()
        self.test_query = "vegetarian Italian pasta dishes"
    
    @patch('gutenberg.recipes_storage_and_retrieval_v2.build_outputs')
    @patch('gutenberg.recipes_storage_and_retrieval_v2.build_self_query_retriever')
    @patch('gutenberg.recipes_storage_and_retrieval_v2.MultiQueryRetriever')
    def test_retrieval_method_comparison(self, mock_multi_query, mock_build_retriever, mock_build_outputs):
        """Test and compare the three retrieval methods side by side."""
        # Setup for similarity search
        sim_docs = [MagicMock(page_content="Classic pasta"), MagicMock(page_content="Vegetable lasagna")]
        self.mock_vector_store.similarity_search.return_value = sim_docs
        
        # Setup for self-query retrieval
        sq_retriever = MagicMock()
        mock_build_retriever.return_value = sq_retriever
        sq_docs = [MagicMock(page_content="Vegetarian spaghetti"), MagicMock(page_content="Plant-based pasta")]
        sq_retriever.invoke.return_value = sq_docs
        
        # Setup for multi-query retrieval
        mq_retriever = MagicMock()
        mock_multi_query.return_value = mq_retriever
        mq_docs = [
            MagicMock(page_content="Vegetarian spaghetti"),  # Duplicate from self-query
            MagicMock(page_content="Penne arrabbiata"),      # New document
            MagicMock(page_content="Mushroom risotto")       # New document
        ]
        mq_retriever.invoke.return_value = mq_docs
        
        # Setup different outputs for each method
        def build_outputs_side_effect(docs, llm):
            if docs == sim_docs:
                return [{"recipe": "similarity_result_1"}, {"recipe": "similarity_result_2"}]
            elif docs == sq_docs:
                return [{"recipe": "self_query_result_1"}, {"recipe": "self_query_result_2"}]
            elif docs == mq_docs:
                return [{"recipe": "multi_query_result_1"}, {"recipe": "multi_query_result_2"}, {"recipe": "multi_query_result_3"}]
            return []
        
        mock_build_outputs.side_effect = build_outputs_side_effect
        
        # Call all three methods
        sim_results = perform_similarity_search(self.test_query, self.mock_llm, self.mock_vector_store)
        sq_results = perform_self_query_retrieval(self.test_query, self.mock_llm, self.mock_vector_store, self.mock_translator)
        mq_results = perform_multi_query_retrieval(self.test_query, self.mock_llm, self.mock_vector_store, self.mock_translator)
        
        # Verify results
        self.assertEqual(len(sim_results), 2)
        self.assertEqual(len(sq_results), 2)
        self.assertEqual(len(mq_results), 3)  # Multi-query should retrieve more diverse results
        
        # Verify multi-query has more results than the other methods
        self.assertGreater(len(mq_results), len(sim_results))
        self.assertGreater(len(mq_results), len(sq_results))

class TestAgentToolIntegration(unittest.TestCase):
    """Test the integration of different retrieval methods as ReAct Agent tools."""
    
    @patch('app.json.dumps')
    @patch('app.perform_recipes_similarity_search')
    def test_similarity_search_tool(self, mock_search, mock_dumps):
        """Test that the similarity search tool correctly formats results."""
        from app import create_recipes_similarity_search_tool
        
        # Setup
        mock_search.return_value = [{"recipe": "test recipe"}]
        mock_dumps.return_value = '{"result": "json string"}'
        
        # Create the tool and call it
        tool = create_recipes_similarity_search_tool()
        result = tool.invoke("test query")
        
        # Verify the search was performed and results were formatted
        mock_search.assert_called_once()
        mock_dumps.assert_called_once_with([{"recipe": "test recipe"}], default=str)
        self.assertEqual(result, '{"result": "json string"}')
    
    @patch('app.json.dumps')
    @patch('app.perform_recipes_self_query_retrieval')
    def test_self_query_tool(self, mock_retrieval, mock_dumps):
        """Test that the self-query tool correctly formats results."""
        from app import create_recipes_self_query_tool
        
        # Setup
        mock_retrieval.return_value = [{"recipe": "filtered recipe"}]
        mock_dumps.return_value = '{"result": "json string"}'
        
        # Create the tool and call it
        tool = create_recipes_self_query_tool()
        result = tool.invoke("test query")
        
        # Verify the retrieval was performed and results were formatted
        mock_retrieval.assert_called_once()
        mock_dumps.assert_called_once_with([{"recipe": "filtered recipe"}], default=str)
        self.assertEqual(result, '{"result": "json string"}')
    
    @patch('app.json.dumps')
    @patch('app.perform_recipes_multi_query_retrieval')
    def test_multi_query_tool(self, mock_retrieval, mock_dumps):
        """Test that the multi-query tool correctly formats results."""
        from app import create_recipes_multi_query_tool
        
        # Setup
        mock_retrieval.return_value = [{"recipe": "expanded query result"}]
        mock_dumps.return_value = '{"result": "json string"}'
        
        # Create the tool and call it
        tool = create_recipes_multi_query_tool()
        result = tool.invoke("test query")
        
        # Verify the retrieval was performed and results were formatted
        mock_retrieval.assert_called_once()
        mock_dumps.assert_called_once_with([{"recipe": "expanded query result"}], default=str)
        self.assertEqual(result, '{"result": "json string"}')

if __name__ == '__main__':
    unittest.main()