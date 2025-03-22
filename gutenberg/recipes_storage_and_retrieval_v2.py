import os
import re
import json
import argparse
from dotenv import load_dotenv

# Project Gutenberg
from gutenbergpy.gutenbergcache import GutenbergCache
from gutenbergpy.textget import get_text_by_id

# LangChain
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import SupabaseVectorStore
from langchain.chains.query_constructor.schema import AttributeInfo
from langchain.retrievers.self_query.base import SelfQueryRetriever
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_community.query_constructors.supabase import SupabaseVectorTranslator
from langchain.chains.query_constructor.base import StructuredQueryOutputParser, get_query_constructor_prompt


# Supabase
from supabase import create_client, Client
from supabase.client import ClientOptions


###############################################################################
# NV & GLOBALS
###############################################################################


# Constants
COOKING_KEYWORDS = ["cooking", "recipes", "cookbook", "culinary"]

COMMON_INGREDIENTS = {
    "flour", "sugar", "butter", "salt", "milk", "egg", "vanilla", "baking powder",
    "baking soda", "oil", "water", "yeast", "honey", "cinnamon", "chocolate",
    "garlic", "onion", "tomato", "cheese", "beef", "chicken", "pork", "fish",
    "carrot", "potato", "pepper", "cream", "rice", "pasta", "broth", "vinegar",
    "herbs", "spices", "nuts", "almonds", "walnuts", "raisins", "yeast"
}

RECIPE_TYPE = ["dessert", "soup", "salad", "main course", "appetizer", "beverage"]
CUISINE = ["italian", "french", "german", "australian", "english",  "american", "thai", "japanese", "chinese", "mexican", "indian"]
SPECIAL_CONSIDERATIONS = ["vegetarian", "vegan", "keto", "nut-free", "dairy-free", "gluten-free", "low-carb"]

MAX_TOKENS_PER_CHUNK = 128000  # approximate chunk size limit

HEADINGS = ["INGREDIENTS", "METHOD", "INSTRUCTIONS", "DIRECTIONS"]


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


def construct_metadata(cache, gutenberg_book_id):
    """
    Build minimal metadata from Gutenberg's cache to attach to each chunk.
    """
    query = f"""
        SELECT 
            b.gutenbergbookid AS gutenbergbookid,
            b.dateissued AS dateissued, 
            t.name AS title, 
            GROUP_CONCAT(a.name, '# ') AS authors,
            GROUP_CONCAT(s.name, '# ') AS subjects
        FROM books b
        LEFT JOIN titles t ON b.id = t.bookid
        LEFT JOIN book_authors ba ON b.id = ba.bookid
        LEFT JOIN authors a ON ba.authorid = a.id
        LEFT JOIN book_subjects bs ON b.id = bs.bookid
        LEFT JOIN subjects s ON bs.subjectid = s.id
        WHERE b.gutenbergbookid = {gutenberg_book_id}
        GROUP BY b.id, t.name;
    """
    cursor = cache.native_query(query)

    result = None
    for row in cursor:
        result = row

    if not result:
        print(f"No metadata found for book ID {gutenberg_book_id}.")
        return {
            "gutenberg_id": gutenberg_book_id,
            "title": "Unknown",
            "authors": [],
            "subjects": []
        }

    gutenberg_id, dateissued, title, authors, subjects = result
    if authors is None:
        authors = "Unknown"
    if subjects is None:
        subjects = "Unknown"

    return {
        "gutenberg_id": gutenberg_id,
        "date_issued": dateissued,
        "title": title,
        "authors": authors.split("# ") if authors else [],
        "subjects": subjects.split("# ") if subjects else [],
    }


###############################################################################
# DISCLAIMER REMOVAL
###############################################################################

def remove_gutenberg_disclaimers(book_text: str) -> str:
    """
    Removes Project Gutenberg headers/footers and lines with 'gutenberg', 'license', or URLs.
    """
    start_marker = re.search(
        r"(\*\*\* START OF THIS PROJECT GUTENBERG EBOOK.*?\*\*\*)",
        book_text, re.IGNORECASE | re.DOTALL
    )
    end_marker = re.search(
        r"(\*\*\* END OF THIS PROJECT GUTENBERG EBOOK.*?\*\*\*)",
        book_text, re.IGNORECASE | re.DOTALL
    )

    if start_marker and end_marker:
        start_idx = start_marker.end()
        end_idx = end_marker.start()
        book_text = book_text[start_idx:end_idx]

    filtered_lines = []
    for line in book_text.splitlines():
        lower_line = line.lower()
        if ("gutenberg" in lower_line or
            "license" in lower_line or
            "www." in lower_line or
            "http" in lower_line):
            continue
        filtered_lines.append(line)
    return "\n".join(filtered_lines)


###############################################################################
# PRE-PROCESSING FIX FOR INLINE TITLES
###############################################################################

def fix_inlined_titles(text: str) -> str:
    """
    Insert a newline after uppercase words that might be a recipe title
    followed immediately by 'Makes', 'Serves', or a digit, etc.
    """
    pattern = re.compile(
        r'([A-Z]{2,}(?:\s+[A-Z]{2,}){0,6})(?=(Makes|Serves|\d|[^a-z\s]))'
    )

    def insert_newline(match):
        return match.group(1) + "\n"

    fixed_text = re.sub(pattern, insert_newline, text)
    return fixed_text


###############################################################################
# RECIPE DETECTION HELPERS
###############################################################################

def is_recipe_title(line: str) -> bool:
    """
    Checks if a line is likely a recipe title:
      - short (under ~15 words)
      - uppercase ratio or 'No. <digits>'
      - all words capitalized
    """
    line = line.strip()
    if not line:
        return False

    skip_words = ["chapter", "license", "project gutenberg", "www.", "http"]
    if any(sw in line.lower() for sw in skip_words):
        return False

    words = line.split()
    if len(words) == 0 or len(words) > 15:
        return False

    if re.match(r"^No\.\s*\d+", line, re.IGNORECASE):
        return True
    if re.match(r"^Recipe\s+No\.\s*\d+", line, re.IGNORECASE):
        return True

    # uppercase ratio
    alpha_chars = [c for c in line if c.isalpha()]
    if alpha_chars:
        uppercase_chars = [c for c in alpha_chars if c.isupper()]
        uppercase_ratio = len(uppercase_chars) / len(alpha_chars)
        if uppercase_ratio > 0.7:
            return True

    # all words capitalized
    capitalized_words = sum(1 for w in words if w and w[0].isupper())
    if capitalized_words == len(words):
        return True

    return False


def is_recipe_heading(paragraph: str) -> bool:
    """
    Check if a paragraph is a known heading (like "INGREDIENTS:", etc.).
    """
    p = paragraph.strip()
    # uppercase or ends with a colon
    if p.isupper() or p.endswith(":"):
        return True
    for h in HEADINGS:
        if h in p.upper():
            return True
    return False


###############################################################################
# EXTRACTION WITH "OVERSAMPLING" & MULTIPLE TITLES
###############################################################################

def extract_all_recipes_with_context(book_text: str, oversample=1):
    """
    Extract recipes by:
      1. Splitting text into paragraphs
      2. Searching for lines that look like recipe titles
      3. When a new title is found, finalize the previous recipe
      4. Oversample = also include `N` paragraphs before
      5. If multiple titles occur in same paragraph, handle them separately
    """
    raw_paragraphs = book_text.split("\n\n")
    paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]

    expanded_paragraphs = []
    for para in paragraphs:
        lines = para.splitlines()
        tmp_buffer = []
        for line in lines:
            line_stripped = line.strip()
            if is_recipe_title(line_stripped):
                if tmp_buffer:
                    expanded_paragraphs.append("\n".join(tmp_buffer).strip())
                    tmp_buffer = []
                expanded_paragraphs.append(line_stripped)
            else:
                tmp_buffer.append(line_stripped)
        if tmp_buffer:
            expanded_paragraphs.append("\n".join(tmp_buffer).strip())

    recipes = []
    current_recipe = []
    in_recipe = False

    i = 0
    while i < len(expanded_paragraphs):
        p = expanded_paragraphs[i].strip()

        if is_recipe_title(p):
            if in_recipe and current_recipe:
                recipes.append("\n\n".join(current_recipe))
                current_recipe = []
            in_recipe = True

            start_idx = max(0, i - oversample)
            for back_idx in range(start_idx, i):
                if expanded_paragraphs[back_idx] not in current_recipe:
                    current_recipe.append(expanded_paragraphs[back_idx])
            current_recipe.append(p)

        else:
            if in_recipe:
                if is_recipe_heading(p):
                    current_recipe.append(p)
                else:
                    current_recipe.append(p)

        i += 1

    if in_recipe and current_recipe:
        recipes.append("\n\n".join(current_recipe))

    return recipes


###############################################################################
# LLM-BASED RECIPE PARSING (Single Call for Full Metadata)
###############################################################################

def extract_recipe_info(chunk_text: str, llm: ChatOpenAI) -> dict:
    """
    Single call to the LLM that extracts:
      - recipe_found (bool)
      - title (str)
      - ingredients (list of str)
      - instructions (str)
      - recipe_type, cuisine, special_considerations
    """
    system_prompt = (
        "You are a helpful assistant that identifies and extracts recipes from text. "
        "Return your answer in valid JSON. If no recipe is present, return "
        '{"recipe_found": false}.\n\n'
        "If a recipe is found, return a JSON object with:\n"
        "{\n"
        '  "recipe_found": true,\n'
        '  "title": "STRING",\n'
        '  "ingredients": ["LIST OF INGREDIENTS" (lowercase, no quantities)],\n'
        '  "instructions": "STRING with instructions",\n'
        f'  "recipe_type": "STRING or LIST from {RECIPE_TYPE}",\n'
        f'  "cuisine": "STRING from {CUISINE}",\n'
        f'  "special_considerations": "STRING or LIST from {SPECIAL_CONSIDERATIONS}"\n'
        "}\n\n"
        "Output must be valid JSON."
    )

    user_prompt = (
        f"Text chunk:\n{chunk_text}\n\n"
        "Does this text contain a recipe? If yes, extract the JSON data above. "
        "If no recipe is present, return {\"recipe_found\": false}."
    )

    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response: AIMessage = llm.invoke(messages)
        reply = response.content.strip()
        recipe_data = json.loads(reply)
        print(f"\nChunk: {chunk_text}")
        print("\n************\n")
        print(f"LLM reply: {recipe_data} \n")
        return recipe_data
    except Exception as e:
        print(f"LLM parsing error: {e}")
        return {"recipe_found": False}


###############################################################################
# TOKEN COUNT & VARIABLE-SIZED CHUNKING
###############################################################################

def approximate_token_count(text: str) -> int:
    """
    Rough token estimate.
    """
    words = text.split()
    return int(len(words) * 1.3)


###############################################################################
# DOWNLOAD, EXTRACT, OVERSAMPLE, LLM-VALIDATE, & STORE
###############################################################################

def download_and_store_books(matching_books, cache, llm, vector_store, oversample=1):
    """
    Pipeline:
      1. Download text
      2. Remove disclaimers
      3. Fix inline titles
      4. Extract recipes with oversampling
      5. Possibly subdivide big chunks
      6. Single LLM call that returns all metadata
      7. Store recognized recipe in Supabase
    """
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=MAX_TOKENS_PER_CHUNK, chunk_overlap=200)
    documents = []

    for gutenberg_book_id, title in matching_books:
        print(f"Processing: {title} (ID: {gutenberg_book_id})")

        try:
            metadata = construct_metadata(cache, gutenberg_book_id)

            raw_text = get_text_by_id(gutenberg_book_id)
            if not raw_text:
                print(f"Unable to retrieve content for ID {gutenberg_book_id}.")
                continue

            content = raw_text.decode("utf-8", errors="ignore")

            content = remove_gutenberg_disclaimers(content)
            content = fix_inlined_titles(content)

            recipe_texts = extract_all_recipes_with_context(content, oversample=oversample)

            for i, recipe_text in enumerate(recipe_texts):
                token_count = approximate_token_count(recipe_text)

                if token_count <= MAX_TOKENS_PER_CHUNK:
                    sub_chunks = [recipe_text]
                else:
                    sub_chunks = text_splitter.split_text(recipe_text)

                for j, sub_chunk in enumerate(sub_chunks):
                    recipe_info = extract_recipe_info(sub_chunk, llm)
                    if recipe_info.get("recipe_found"):
                        chunk_metadata = metadata.copy()
                        chunk_metadata["recipe_index"] = i
                        chunk_metadata["sub_chunk_index"] = j
                        chunk_metadata["token_count"] = approximate_token_count(sub_chunk)

                        chunk_metadata["recipe_title"] = recipe_info.get("title", "")
                        chunk_metadata["ingredients"] = recipe_info.get("ingredients", [])
                        chunk_metadata["recipe_type"] = recipe_info.get("recipe_type", "")
                        chunk_metadata["cuisine"] = recipe_info.get("cuisine", "")
                        chunk_metadata["special_considerations"] = recipe_info.get("special_considerations", "")

                        formatted_recipe = (
                            f"Title: {recipe_info.get('title')}\n\n"
                            f"Ingredients: {recipe_info.get('ingredients')}\n\n"
                            f"Instructions: {recipe_info.get('instructions')}\n\n"
                        )
                        
                        document = Document(page_content=formatted_recipe, metadata=chunk_metadata)
                        documents.append(document)

        except Exception as e:
            print(f"Error processing {title} (ID: {gutenberg_book_id}): {e}")

    batch_size = 50
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i+batch_size]
        try:
            vector_store.add_documents(batch)
            print(f"Successfully uploaded batch {i//batch_size + 1} "
                  f"of {len(documents)//batch_size + 1}.")
        except Exception as e:
            print(f"Error storing batch {i//batch_size + 1}: {e}")


###############################################################################
# BASELINE SIMILARITY SEARCH (SINGLE-QUERY)
###############################################################################

def perform_similarity_search(query, llm, vector_store):
    """
    Perform similarity search using LangChain.
    """
    recipes = vector_store.similarity_search(query)

    return build_outputs(recipes, llm)


###############################################################################
# SELF-QUERY RETRIEVER
###############################################################################

def build_self_query_retriever(llm, vector_store, structured_query_translator):
    metadata_field_info = [
        AttributeInfo(
            name="recipe_title",
            description="The title of the recipe. Use the like operator for partial matches.",
            type="string",
        ),
        AttributeInfo(
            name="recipe_type",
            description=f"The type of recipe (e.g., {RECIPE_TYPE}).",
            type="string",
        ),
        AttributeInfo(
            name="cuisine",
            description=f"The cuisine type (e.g., {CUISINE}). Use like operator for partial matches.",
            type="string",
        ),
        AttributeInfo(
            name="special_considerations",
            description=f"Dietary restrictions (e.g., {SPECIAL_CONSIDERATIONS}). Use like operator for partial matches.",
            type="list[string]",
        ),
        AttributeInfo(
            name="ingredients",
            description=f"Key ingredients (e.g., {COMMON_INGREDIENTS}). Use like operator for partial matches.",
            type="list[string]",
        ),
    ]

    doc_content_desc = "Text content describing a cooking recipe"
    examples = [
        (
            "Show me all American dessert recipes but not vegetarian.",
            {
                "query": "American dessert",
                "filter": """and(
                                eq("cuisine", 'american'), 
                                eq("recipe_type", 'dessert'), 
                                ne("special_considerations", 'vegetarian')
                            )"""
            }
        ),
        # add more examples...
    ]

    prompt = get_query_constructor_prompt(
        doc_content_desc,
        metadata_field_info,
        examples=examples
    )

    output_parser = StructuredQueryOutputParser.from_components()
    query_constructor = prompt | llm | output_parser

    sq_retriever = SelfQueryRetriever(
        query_constructor=query_constructor,
        vectorstore=vector_store,
        structured_query_translator=structured_query_translator,
    )

    return sq_retriever

def perform_self_query_retrieval(query, llm, vector_store, structured_query_translator):
    """
    Creates a SelfQueryRetriever for metadata fields about recipes.
    """
    retriever = build_self_query_retriever(llm, vector_store, structured_query_translator)

    recipes = retriever.invoke(query)

    return build_outputs(recipes, llm)


def build_outputs(results, llm):
    outputs = []

    for i, res in enumerate(results, start=1):
        processed_output = {
            "recipe": res.page_content,
            "metadata": res.metadata
        }
        outputs.append(processed_output)

    return outputs

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
    
    # Set default behavior: use similarity search if neither is specified
    if not args.use_similarity_search and not args.use_self_query_retrieval:
        args.use_similarity_search = True
    
    top_n = args.top_n
    start_date = args.start_date
    end_date = args.end_date

    load_dotenv(override=True)

    SUPABASE_URL = os.getenv("SUPABASE_HTTPS_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    supabase_client: Client = create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(
            postgrest_client_timeout=360,
            storage_client_timeout=360,
            schema="public"
        )
    )

    chat_llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0,
        openai_api_key=OPENAI_API_KEY
    )

    # We'll keep the same LLM for classification calls
    classifier_llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        openai_api_key=OPENAI_API_KEY
    )


    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)

    recipes_vector_store = SupabaseVectorStore(
        client=supabase_client,
        embedding=embeddings,  
        table_name="recipes_v2",
        query_name="match_recipes_v2"
    )

    cache = GutenbergCache.get_cache()

    if args.load_books:
        print("Searching for cooking-related books...")
        matching_books = search_gutenberg_titles(
            cache,
            keywords=COOKING_KEYWORDS,
            top_n=top_n,
            start_date=start_date,
            end_date=end_date
        )
        print(f"Found {len(matching_books)} books.")
        print("Downloading and storing books...")
        oversample_distance = 1
        download_and_store_books(
            matching_books,
            cache,
            classifier_llm,  # here you call the parse LLM
            recipes_vector_store,
            oversample=oversample_distance
        )

    results = None

    query = args.query
    
    # ================== Decide which retrieval to use ================== #
    if args.use_similarity_search:
        print(f"\nSimilarity search with: {query}")
        results = perform_similarity_search(query, chat_llm, recipes_vector_store)
    elif args.use_self_query_retrieval:
        print(f"\nSelf-query retrieval with: {query}")
        results = perform_self_query_retrieval(query, chat_llm, recipes_vector_store, SupabaseVectorTranslator())
    # =================================================================== #

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
