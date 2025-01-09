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
                    "source": title, # Key must be named source for compatibility with LangChain
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
            vector_store.add_documents(
                batch
            )
            print(f"Successfully uploaded batch {i//batch_size + 1} "
                  f"of {len(documents)//batch_size + 1}.")
        except Exception as e:
            print(f"Error storing batch {i // batch_size + 1}: {e}")


def perform_similarity_search(query, vector_store):
    """Perform a similarity search using LangChain."""
    print("Performing similarity search...")
    return vector_store.similarity_search(query)

###############################################################################
# MAIN
###############################################################################

def main():
    parser = argparse.ArgumentParser(
        description="Loading and testing a vector store."
    )
    
    parser.add_argument("-lb", "--load_books", type=bool, default=False, help="Search and load books.")
    
    parser.add_argument("-n", "--top_n", type=int, default=3, help="Number of books to load.")
    
    parser.add_argument("-sd", "--start_date", type=str, default="1950-01-01", help="Search start date.")

    parser.add_argument("-ed", "--end_date", type=str, default="2000-12-31", help="Search end date.")
    
    # Parse the arguments
    args = parser.parse_args()
    
    top_n = args.top_n
    start_date = args.start_date
    end_date = args.end_date

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

    # Perform query
    query = "How to bake a cake"
    print(f"Performing similarity search with: {query}")
    results = perform_similarity_search(query, vector_store)

    for i, res in enumerate(results, start=1):
        snippet = res.page_content[:500].replace("\n", " ") + "..."
        print(f"[Result {i}] Snippet: {snippet}")
        print(f"Metadata: {res.metadata}")
        print("-" * 70)

if __name__ == "__main__":
    main()