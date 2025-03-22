import os
import argparse
from dotenv import load_dotenv

# Project Gutenberg
from gutenbergpy.gutenbergcache import GutenbergCache
from gutenbergpy.textget import get_text_by_id

# LangChain & Vector Store
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import SupabaseVectorStore
from langchain.chains.query_constructor.schema import AttributeInfo
from langchain.retrievers.self_query.base import SelfQueryRetriever

# Supabase
from supabase import create_client, Client
from supabase.client import ClientOptions

#spaCy
import spacy

###############################################################################
# NV & GLOBALS
###############################################################################

# Constants
# Define a list of keywords to search for in Project Gutenberg
COOKING_KEYWORDS = ["cooking", "recipes", "cookbook", "culinary"]

# Define a list of common ingredients for filtering
COMMON_INGREDIENTS = {
    "flour", "sugar", "butter", "salt", "milk", "egg", "vanilla", "baking powder",
    "baking soda", "oil", "water", "yeast", "honey", "cinnamon", "chocolate",
    "garlic", "onion", "tomato", "cheese", "beef", "chicken", "pork", "fish",
    "carrot", "potato", "pepper", "cream", "rice", "pasta", "broth", "vinegar",
    "herbs", "spices", "nuts", "almonds", "walnuts", "raisins", "yeast"
}

# Define lists of recipe types, cuisines, and special considerations

RECIPE_TYPE = ["dessert", "soup", "salad", "main course", "appetizer", "beverage"]

CUISINE = ["italian", "french", "german", "australian", "english",  "american", "thai", "japanese", "chinese", "mexican", "indian"]

SPECIAL_CONSIDERATIONS = ["vegetarian", "vegan", "keto", "nut-free", "dairy-free", "gluten-free", "low-carb"]   

# Global for spaCy NLP model
nlp = None

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


# TODO: Define the extract_metadata_nlp function to implement the heuristic-based for NLP metadata extraction


# TODO: Define the construct_metadata function to build a metadata dictionary for each recipe


###############################################################################
# DOWNLOAD, EXTRACT, & STORE
###############################################################################

def download_and_store_books(matching_books, cache, vector_store):
    """
    Pipeline:
      1. Download text
      2. Extract metadata using NLP
      3. Split text into chunks
      4. Store chunks in Supabase 
    """
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    documents = []

    for gutenberg_book_id, title in matching_books:
        print(f"Processing: {title} (ID: {gutenberg_book_id})")
        try:
            metadata = construct_metadata(gutenberg_book_id, cache)
            raw_text = get_text_by_id(gutenberg_book_id)
            content = raw_text.decode("utf-8", errors="ignore")
            chunks = text_splitter.split_text(content)

            for i, chunk in enumerate(chunks):
                chunk_metadata = metadata.copy()
                chunk_metadata["chunk_index"] = i
                chunk_metadata["content_length"] = len(chunk)
                document = Document(page_content=chunk, metadata=chunk_metadata)
                documents.append(document)
                # print(document)

        except Exception as e:
            print(f"Error processing {title}: {e}")

    #Batch upload documents to Supabase
    batch_size = 50  # Adjust as necessary
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        try:
            vector_store.add_documents(
                batch
            )
            print(f"Successfully uploaded batch {i//batch_size + 1} "
                  f"of {len(documents)//batch_size + 1}.")
        except Exception as e:
            print(f"Error storing batch {i // batch_size + 1}: {e}")


###############################################################################
# BASELINE SIMILARITY SEARCH (SINGLE-QUERY)
###############################################################################

# TODO: Perform a vector-based similarity search


###############################################################################
# SELF-QUERY RETRIEVER
###############################################################################

# TODO: Perform a self-query retrieval


# TODO: Define a function named build_outputs to create a standard output format from the data returned by the similarity search and self-query retrieval functions


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
    parser.add_argument("-q", "--query", type=str, default="Find Poached Eggs Recipes.", help="Query to perform.")
    parser.add_argument("-ss", "--use_similarity_search", action="store_true", help="Use similarity search.")
    parser.add_argument("-sr", "--use_self_query_retrieval", action="store_true", help="Use self query retrieval.")
    
    # Parse the arguments
    args = parser.parse_args()
    
    # TODO: Add conditional statement to run the use_similarity_search function if no flag is specified
    # Set default behavior: use similarity search if neither is specified


    top_n = args.top_n
    start_date = args.start_date
    end_date = args.end_date

    # Attempt spaCy load
    global nlp

    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        print("Please install the spaCy en_core_web_sm model:")
        print("  python -m spacy download en_core_web_sm")
        raise

    # Load environment variables
    load_dotenv(override=True) # Load environment variables from .env

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

    # Initialize embeddings & LLMs
    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)

    chat_llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0,
        openai_api_key=OPENAI_API_KEY
    )

    vector_store = SupabaseVectorStore(
        client=supabase_client,
        embedding=embeddings,
        table_name="recipes",
        query_name="match_recipes"
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

        # Download, oversample paragraphs by 1 on each side for context
        print("Downloading and storing books...")
        download_and_store_books(matching_books, cache, vector_store)


    # Perform query
    query = args.query
    results = []
    
    if args.use_similarity_search:
        print(f"\nSimilarity search with: {query}")
        results = perform_similarity_search(query, chat_llm, vector_store)
    elif args.use_self_query_retrieval:
        print(f"\nSelf-query retrieval with: {query}")
        results = perform_self_query_retrieval(query, chat_llm, vector_store)
    
    # Print out the results
    # Check if results is None or empty
    if not results:
        print(f"\nNo results found for query: {query}")
    else:
        for i, res in enumerate(results, start=1):
            print(f"\n[Result {i}] Recipe: {res['recipe']}")
            print(f"[Metadata] {res['metadata']}")
            print("-" * 70)


if __name__ == "__main__":
    main()
