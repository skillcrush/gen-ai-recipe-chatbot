import os
import argparse
from dotenv import load_dotenv

# Additional imports for the two new variants
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, FewShotChatMessagePromptTemplate

# Project Gutenberg
from gutenbergpy.gutenbergcache import GutenbergCache
from gutenbergpy.textget import get_text_by_id

# LangChain & Vector Store
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import SupabaseVectorStore
from langchain.chains import RetrievalQAWithSourcesChain
from langchain import hub

# Supabase
from supabase import create_client, Client
from supabase.client import ClientOptions

###############################################################################
# NV & GLOBALS
###############################################################################

# Constants
COOKING_KEYWORDS = ["cooking", "recipes", "cookbook", "culinary"]

###############################################################################
# GUTENBERG SEARCH & METADATA
###############################################################################

def search_gutenberg_titles(cache, keywords, top_n=10, start_date=None, end_date=None):
    """
    Search Project Gutenberg for cooking-related books, optionally filtered by date.
    Returns: List of (gutenbergbookid, title).
    """
    matching_books = []
    keyword_filters = " OR ".join([f"s.name LIKE '%{kw}%'" for kw in keywords])

    date_filter = ""
    if start_date and end_date:
        date_filter = f"AND b.dateissued BETWEEN '{start_date}' AND '{end_date}'"
    elif start_date:
        date_filter = f"AND b.dateissued >= '{start_date}'"
    elif end_date:
        date_filter = f"AND b.dateissued <= '{end_date}'"

    query = f"""
        SELECT DISTINCT b.gutenbergbookid AS gutenbergbookid, t.name AS title
        FROM books b
        LEFT JOIN titles t ON b.id = t.bookid
        LEFT JOIN book_subjects bs ON b.id = bs.bookid
        LEFT JOIN subjects s ON bs.subjectid = s.id
        WHERE ({keyword_filters}) {date_filter}
        LIMIT {top_n};
    """
    results = cache.native_query(query)
    for row in results:
        gutenbergbookid, title = row
        matching_books.append((gutenbergbookid, title))
    return matching_books

def download_and_store_books(matching_books, vector_store):
    """Download books, split text, generate embeddings, and store in Supabase."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )

    documents = []

    for book_id, title in matching_books:
        print(f"Processing: {title} (ID: {book_id})")
        try:
            # Download book content
            raw_text = get_text_by_id(book_id)
            content = raw_text.decode("utf-8", errors="ignore")  # Decode to string

            # Split the text into manageable chunks
            chunks = text_splitter.split_text(content)

            for i, chunk in enumerate(chunks):
                # Construct metadata as a JSON object
                metadata = {
                    "source": title,  # Key must be 'source' for LangChain
                    "gutenberg_id": str(book_id),
                    "chunk_index": i,
                    "content_length": len(chunk)
                }

                # Create a Document object
                documents.append(Document(page_content=chunk, metadata=metadata))

        except Exception as e:
            print(f"Error processing {title}: {e}")

    # Batch insert documents to Supabase
    batch_size = 50  # Adjust as necessary
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        try:
            vector_store.add_documents(batch)
            print(f"Successfully uploaded batch {i // batch_size + 1} "
                  f"of {len(documents) // batch_size + 1}.")
        except Exception as e:
            print(f"Error storing batch {i // batch_size + 1}: {e}")

###############################################################################
# RAG FUNCTIONS
###############################################################################

###############################################################################
# Retrieval QA
###############################################################################

def perform_retrieval_qa(query, llm, vector_store):
    """
    Perform a retrieval QA using LangChain. 
    Returns a unified data structure.
    """
    print("Performing retrieval qa...")
    books_retriever = vector_store.as_retriever(search_kwargs={"k": 3})
    chain = RetrievalQAWithSourcesChain.from_chain_type(
        llm=llm, 
        retriever=books_retriever, 
        chain_type="stuff", 
        return_source_documents=True
    )

    chain_result = chain.invoke({"question": query})
    # chain_result typically:
    # {
    #   "answer": "...",
    #   "sources": "...",
    #   "source_documents": [...],
    # }

    return {
        "method": "retrieval_qa",
        "query": query,
        "results": [
            {
                "sub_query": query,  # same as main query
                "answer": chain_result.get("answer"),
                "sources": chain_result.get("sources"),
                "source_documents": chain_result.get("source_documents", [])
            }
        ]
    }

###############################################################################
# Similiarity Search
###############################################################################

def perform_similarity_search(query, vector_store):
    """
    Perform a similarity search using LangChain, returning a unified data structure.
    """
    print("Performing similarity search...")
    docs = vector_store.similarity_search(query)

    # Wrap each Document in an item of the "results" list
    results_list = []
    for doc in docs:
        results_list.append({
            "sub_query": query,
            "answer": None,  # No LLM answer, just raw search results
            "sources": doc.metadata.get("source") if doc.metadata else None,
            "source_documents": [doc]
        })

    return {
        "method": "similarity_search",
        "query": query,
        "results": results_list
    }


###############################################################################
# RAG Step-Back Prompting
###############################################################################

def perform_rag_step_back_prompting(query, llm, vector_store):
    """
    Step-Back Prompting

    1) Generate a more generic/paraphrased "step-back" question.
    2) Retrieve context for the original question and the step-back question.
    3) Combine both contexts to produce a final comprehensive answer.
    4) Return an output data structure consistent with other RAG functions.
    """

    print("[RAG Step-Back Prompting]")

    # --------------------------------------------------------------------------
    # 1) Define few-shot examples and set up the step-back prompt
    # --------------------------------------------------------------------------

    examples = [
        {
            "input": "How do I bake a chocolate cake from scratch?",
            "output": "What is the general process of baking a cake from scratch?",
        },
        {
            "input": "What are the health benefits of using olive oil instead of butter in cooking?",
            "output": "What is the general difference between cooking with olive oil and cooking with butter?",
        },
    ]

    # Create an example-based prompt to demonstrate how to transform questions
    example_prompt = ChatPromptTemplate.from_messages(
        [
            ("human", "{input}"), 
            ("ai", "{output}"),
        ]
    )
    few_shot_prompt = FewShotChatMessagePromptTemplate(
        example_prompt=example_prompt,
        examples=examples,
    )

    # Wrap these few-shot examples in a final system+user prompt
    step_back_system_message = (
        "You are an expert at cooking knowledge. Your task is to step back "
        "and paraphrase a question to a more generic step-back question, "
        "which is easier to answer. Here are a few examples:"
    )
    step_back_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", step_back_system_message),
            few_shot_prompt,  # few-shot examples
            ("user", "{question}"),
        ]
    )

    # Construct a small "chain" that calls the LLM and parses out the string
    generate_queries_step_back = step_back_prompt | llm | StrOutputParser()

    # --------------------------------------------------------------------------
    # 2) Retrieve context using the original question
    # --------------------------------------------------------------------------
    retriever = vector_store.as_retriever(search_kwargs={"k": 3})
    normal_docs = retriever.invoke(query)

    # --------------------------------------------------------------------------
    # 3) Generate the step-back question & retrieve context for it
    # --------------------------------------------------------------------------
    step_back_question = generate_queries_step_back.invoke({"question": query})
    step_back_docs = retriever.invoke(step_back_question)

    # --------------------------------------------------------------------------
    # 4) Build a final synthesis prompt that references both contexts
    # --------------------------------------------------------------------------
    response_prompt_template = """You are an expert of cooking knowledge. 
    I am going to ask you a question. Your response should be comprehensive and 
    should not contradict the following context if it is relevant. If it is not 
    relevant, ignore it.

    # Normal Context:
    {normal_context}

    # Step-Back Context:
    {step_back_context}

    # Original Question: {question}
    # Answer:
    """
    response_prompt = ChatPromptTemplate.from_template(response_prompt_template)

    # Flatten the retrieved docs into strings
    normal_context_str = "\n\n".join([doc.page_content for doc in normal_docs])
    step_back_context_str = "\n\n".join([doc.page_content for doc in step_back_docs])

    # Prepare the final LLM input
    final_input = {
        "normal_context": normal_context_str,
        "step_back_context": step_back_context_str,
        "question": query,
    }

    # Synthesize the final answer
    final_answer = (response_prompt | llm | StrOutputParser()).invoke(final_input)

    # --------------------------------------------------------------------------
    # 5) Return a structure consistent with other RAG methods
    # --------------------------------------------------------------------------
    # Optionally, combine docs or keep them separate
    combined_docs = normal_docs + step_back_docs

    return {
        "method": "rag_step_back_prompting",
        "query": query,
        "results": [
            {
                # You can store the step-back question here, or the original question
                "sub_query": step_back_question,
                "answer": final_answer,
                "sources": None,  # or extract doc metadata
                "source_documents": combined_docs
            }
        ]
    }

###############################################################################
# RAG DECOMPOSITION
###############################################################################

def perform_rag_decomposition(query, llm, vector_store):
    """
    (Original) Decompose a user query into multiple sub-queries, perform retrieval QA for each,
    and return a unified data structure.
    """
    print("Performing standard RAG decomposition...")
    # 1) Decompose the query
    template = """You are a helpful assistant that generates multiple sub-questions related to an input question.
The goal is to break down the input into a set of sub-problems / sub-questions that can be answered in isolation.
Generate multiple search queries related to: {question}
Output (3 queries):"""
    
    prompt_decomposition = ChatPromptTemplate.from_template(template)
    generate_queries_decomposition = (
        prompt_decomposition 
        | llm
        | StrOutputParser()
        | (lambda x: x.split("\n"))
    )
    
    sub_queries = generate_queries_decomposition.invoke({"question": query})

    # 2) For each sub-query, call your retrieval QA
    rag_results_list = []
    for sub_query in sub_queries:
        clean_sub_query = sub_query.strip("1234567890. )-")
        retrieval_result = perform_retrieval_qa(clean_sub_query, llm, vector_store)
        
        if retrieval_result["results"]:
            item = retrieval_result["results"][0]
            rag_results_list.append(item)
        else:
            rag_results_list.append({
                "sub_query": clean_sub_query,
                "answer": None,
                "sources": None,
                "source_documents": []
            })

    # 3) Build the unified structure
    return {
        "method": "rag_decomposition",
        "query": query,
        "results": rag_results_list
    }

###############################################################################
# RAG Decomposition: Answering Recursively
###############################################################################

def perform_rag_decomposition_answer_recursively(query, llm, vector_store):
    """
    Answer Recursively
    
    This approach simulates building up a "Q&A memory" (q_a_pairs) as you iteratively
    answer queries. For simplicity, we'll demonstrate only a single pass with the
    final question.
    
    In a real-world scenario, you might iterate over multiple questions or keep
    updating q_a_pairs with each new question to refine answers further.
    """

    print("[RAG Decomposition - Answering Recursively]")

    # Prompt template that includes the question, background Q+A pairs, and retrieved context
    template = """Here is the question you need to answer:

    \n --- \n {question} \n --- \n

    Here is any available background question + answer pairs:

    \n --- \n {q_a_pairs} \n --- \n

    Here is additional context relevant to the question: 

    \n --- \n {context} \n --- \n

    Use the above context and any background question + answer pairs to answer the question: {question}
    """

    decomposition_prompt = ChatPromptTemplate.from_template(template)

    # Helper to format Q&A pairs
    def format_qa_pair(q, ans):
        return f"Question: {q}\nAnswer: {ans}".strip()

    # "q_a_pairs" could be updated as you recursively handle more questions
    q_a_pairs = ""

    # Retrieve context from the vector store (e.g., similarity search)
    docs = vector_store.similarity_search(query)
    context = "\n".join([doc.page_content for doc in docs[:3]])

    # Build the prompt input
    prompt_input = {
        "question": query,
        "q_a_pairs": q_a_pairs,
        "context": context
    }

    # Run the chain
    answer = (decomposition_prompt | llm | StrOutputParser()).invoke(prompt_input)

    # Update Q&A pairs (if you wanted to handle multiple queries recursively)
    q_a_pair = format_qa_pair(query, answer)
    q_a_pairs += "\n---\n" + q_a_pair

    # Return data in a similar structure
    return {
        "method": "rag_decomposition_recursive",
        "query": query,
        "results": [
            {
                "sub_query": query,
                "answer": answer,
                "sources": None,  # or you can store doc metadata here
                "source_documents": docs
            }
        ]
    }

###############################################################################
# RAG Decomposition: Answer Individually
###############################################################################

def perform_rag_decomposition_answer_individually(query, llm, vector_store):
    """
    Answer Individually

    1) Decompose the user's query into sub-questions.
    2) Retrieve context and answer each sub-question individually.
    3) Generate a final synthetic answer based on the set of Q+A pairs from all sub-questions.
    4) Return sources for each sub-question, aggregated into the final result.
    """

    print("[RAG Decomposition - Answer Individually]")

    # 1) Sub-question generator chain (similar to the default decomposition approach)
    template_decomp = """You are a helpful assistant that generates multiple sub-questions 
related to an input question. Generate multiple search queries related to: {question}
Output (3 queries):"""
    
    prompt_decomposition = ChatPromptTemplate.from_template(template_decomp)
    generate_queries_decomposition = (
        prompt_decomposition
        | llm
        | StrOutputParser()
        | (lambda x: x.split("\n"))
    )

    # 2) For each sub-question, retrieve docs and do RAG
    prompt_rag = hub.pull("rlm/rag-prompt")

    def retrieve_and_rag(main_question, rag_prompt, sub_question_generator_chain):
        """
        Returns a list of dictionaries, each containing:
        - sub_question: The sub-question text
        - answer: The LLM's answer
        - docs: The list of retrieved docs
        - sources: The 'source' field from each doc's metadata
        """
        sub_questions = sub_question_generator_chain.invoke({"question": main_question})
        all_sub_results = []

        for sub_q in sub_questions:
            sub_q_clean = sub_q.strip("1234567890. )-")

            # Retrieve relevant documents
            docs = vector_store.similarity_search(sub_q_clean)

            # LLM prompt for each sub-question
            answer = (rag_prompt | llm | StrOutputParser()).invoke({
                "context": docs, 
                "question": sub_q_clean
            })

            # Extract sources from each doc’s metadata
            sub_sources = []
            for d in docs:
                # Example metadata field "source"
                if d.metadata and d.metadata.get("source"):
                    sub_sources.append(d.metadata["source"])

            # Build a single structure for each sub-question
            all_sub_results.append({
                "sub_question": sub_q_clean,
                "answer": answer,
                "docs": docs,
                "sources": list(set(sub_sources)),  # deduplicate if needed
            })

        return all_sub_results

    # Execute retrieval & RAG for each sub-question
    rag_results = retrieve_and_rag(query, prompt_rag, generate_queries_decomposition)

    # 3) Format Q+A pairs for final synthesis
    def format_qa_pairs(results_list):
        """
        Given a list of sub-question results, build a multi-line string of Q+A pairs.
        """
        formatted_str = []
        for i, item in enumerate(results_list, start=1):
            q = item["sub_question"]
            a = item["answer"]
            formatted_str.append(f"Question {i}: {q}\nAnswer {i}: {a}\n")
        return "\n".join(formatted_str).strip()

    # Combine sub-answers into a single Q&A string
    context_qa = format_qa_pairs(rag_results)

    # 4) Final prompt to synthesize one overall answer
    final_template = """Here is a set of Q+A pairs:

{context}

Use these to synthesize an answer to the question: {question}
"""
    prompt_final = ChatPromptTemplate.from_template(final_template)

    final_answer = (prompt_final | llm | StrOutputParser()).invoke({
        "context": context_qa,
        "question": query
    })

    # Collect all sources & docs from sub-questions
    all_sources = []
    all_docs = []
    for item in rag_results:
        all_sources.extend(item["sources"])
        all_docs.extend(item["docs"])

    # Deduplicate sources if needed
    all_sources = list(set(all_sources))

    return {
        "method": "rag_decomposition_individual",
        "query": query,
        "results": [
            {
                "sub_query": query,
                "answer": final_answer,
                "sources": all_sources, 
                "source_documents": all_docs  # if you want them all at once
            }
        ]
    }


###############################################################################
# MAIN
###############################################################################

def main():
    parser = argparse.ArgumentParser(
        description="Loading and testing a vector store."
    )
    
    parser.add_argument("-lb", "--load_books", action="store_true", help="Search and load books.")
    parser.add_argument("-n", "--top_n", type=int, default=3, help="Number of books to load.")
    parser.add_argument("-sd", "--start_date", type=str, default="1950-01-01", help="Search start date.")
    parser.add_argument("-ed", "--end_date", type=str, default="2000-12-31", help="Search end date.")
    parser.add_argument("-q", "--query", type=str, default="How to make a sponge cake with fruit flavor?", help="Query for retrieval.")
    parser.add_argument("-ss", "--perform_similarity_search", action="store_true", help="Perform similarity search.")
    parser.add_argument("-rq", "--perform_retrieval_qa", action="store_true", help="Perform retrieval QA.")
    parser.add_argument("-rdsb", "--perform_rag_step_back_prompting", action="store_true", help="Perform RAG with step-back prompting.")
    parser.add_argument("-rd", "--perform_rag_decomposition", action="store_true", help="Perform RAG with decomposition.")
    parser.add_argument("-rdar", "--perform_rag_decomposition_answer_recursively", action="store_true", help="Perform RAG with decomposition and answer recursively.")
    parser.add_argument("-rdai", "--perform_rag_decomposition_answer_individually", action="store_true", help="Perform RAG with decomposition and answer individually.")


    # Parse the arguments
    args = parser.parse_args()

    
    # Set default behavior: use similarity search if neither is specified
    if not args.perform_similarity_search and not args.perform_retrieval_qa and not args.perform_rag_step_back_prompting and not args.perform_rag_decomposition and not args.perform_rag_decomposition_answer_recursively and not args.perform_rag_decomposition_answer_individually:
        args.perform_similarity_search = True
    
    top_n = args.top_n
    start_date = args.start_date
    end_date = args.end_date

    # Load environment variables
    load_dotenv(override=True)  # Load environment variables from .env

    SUPABASE_URL = os.getenv("SUPABASE_HTTPS_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # Initialize Supabase
    supabase_client: Client = create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(
            postgrest_client_timeout=360,
            storage_client_timeout=360,
            schema="public"
        )
    )

    # Initialize embeddings & LLM
    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)

    chat_llm = ChatOpenAI(
        model="gpt-4o",  # or "gpt-3.5-turbo", etc.
        temperature=0,
        openai_api_key=OPENAI_API_KEY
    )

    vector_store = SupabaseVectorStore(
        client=supabase_client,
        embedding=embeddings,
        table_name="books",
        query_name="match_books"
    )

    # Initialize Gutenberg cache
    cache = GutenbergCache.get_cache()

    if args.load_books:
        print("Searching for cooking-related books...")
        # Search & store books from Gutenberg
        matching_books = search_gutenberg_titles(
            cache,
            keywords=COOKING_KEYWORDS,
            top_n=top_n,
            start_date=start_date,
            end_date=end_date
        )
        print(f"Found {len(matching_books)} books.")

        for book_id, title in matching_books:
            print(f"Processing: {title} (ID: {book_id})")

        print("Downloading and storing books...")
        download_and_store_books(matching_books, vector_store)

    # Perform a sample query
    query = args.query
    print(f"Running query: {query}")

    if args.perform_similarity_search:
        results = perform_similarity_search(query, vector_store)
    elif args.perform_retrieval_qa:
        results = perform_retrieval_qa(query, chat_llm, vector_store)
    elif args.perform_rag_step_back_prompting:
        results = perform_rag_step_back_prompting(query, chat_llm, vector_store)
    elif args.perform_rag_decomposition:
        results = perform_rag_decomposition(query, chat_llm, vector_store)
    elif args.perform_rag_decomposition_answer_recursively:
        results = perform_rag_decomposition_answer_recursively(query, chat_llm, vector_store)
    elif args.perform_rag_decomposition_answer_individually:
        results = perform_rag_decomposition_answer_individually(query, chat_llm, vector_store)
    else:
        print("No operation selected. Use the CLI flags to choose an operation.")
        return

    # Print out the results
    if not results:
        print(f"\nNo results found for query: {query}")
    else:
        for i, res in enumerate(results['results'], start=1):
            print(f"\n[Query {i}]: {res['sub_query']}")
            print("\n[Answer]")
            print(res["answer"])
            print("\n[Source Documents]\n")
            for doc in res["source_documents"]:
                print("\n[Source]", doc.metadata.get("source"))
                print("\n[Content]", doc.page_content)
            print("-" * 70)


if __name__ == "__main__":
    main()
