# Test Suite for GARC Application

This directory contains tests for the GARC application, focusing on multi-query retrieval and hybrid search functionality as implemented in the `07-query-translation` branch.

## Test Files

- `test_multi_query_retrieval.py`: Tests for core multi-query retrieval functionality
- `test_hybrid_search.py`: Tests for hybrid search combining multiple retrieval methods
- `integration_test_multi_query.py`: Tests for integration of multi-query with ReAct agent

## Running Tests

Run all tests from the project root directory:

```bash
python -m pytest tests/
```

Run specific test files:

```bash
python -m pytest tests/test_multi_query_retrieval.py
```

Run tests with verbose output:

```bash
python -m pytest tests/ -v
```

## Test Coverage

These tests cover the following functionality:

1. **Multi-Query Retrieval**
   - Query expansion using LLM to generate query variations
   - LineListOutputParser for processing multiline query variations
   - Integration with self-query retrieval

2. **Hybrid Search**
   - Similarity search retrieval
   - Self-query retrieval with metadata filtering
   - Multi-query retrieval combining the above methods
   - Comparative analysis of retrieval results

3. **ReAct Agent Integration**
   - Tool creation for all retrieval methods
   - Agent configuration with appropriate tools
   - Dynamic tool selection based on query type