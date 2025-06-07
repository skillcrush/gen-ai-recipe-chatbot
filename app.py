import os
import time
import json
import logging
import datetime
from dotenv import load_dotenv

# Flask imports
from flask import Flask, render_template, request, redirect, url_for, flash, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Supabase imports
from supabase import create_client
from supabase.client import ClientOptions

# LangChain imports
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_core.messages import SystemMessage, HumanMessage

from langchain.agents import tool
from langchain_community.query_constructors.supabase import SupabaseVectorTranslator
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver


# RAG imports
from gutenberg.books_storage_and_retrieval import (
    perform_similarity_search as perform_books_similarity_search,
    perform_retrieval_qa as perform_books_retrieval_qa,
)

from gutenberg.recipes_storage_and_retrieval_v2 import (
    perform_similarity_search as perform_recipes_similarity_search,
    perform_self_query_retrieval as perform_recipes_self_query_retrieval,
    perform_multi_query_retrieval as perform_recipes_multi_query_retrieval,
)

# Load environment variables from a .env file
load_dotenv(override=True)

# Set up logging to stream to console only (GAE doesn't allow file writing)
log = logging.getLogger("assistant")
log.setLevel(logging.INFO)

# Log to console for debugging
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
log.addHandler(console_handler)

# Import and configure OpenAI
from langchain_openai import ChatOpenAI
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Missing OPENAI_API_KEY in environment variables.")

chat_llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key)

# Flask app setup
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "mysecret")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("SUPABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Database setup
db = SQLAlchemy(app)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Temporarily disable login for testing
app.config['LOGIN_DISABLED'] = True

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Initialize Supabase and LangChain components

supabase_https_url = os.getenv("SUPABASE_HTTPS_URL")
supabase_key = os.getenv("SUPABASE_KEY")

supabase_client = create_client(supabase_https_url, supabase_key, options=ClientOptions(
    postgrest_client_timeout=120,
    storage_client_timeout=120,
    schema="public",
  ))

embeddings = OpenAIEmbeddings(openai_api_key=api_key)

books_vector_store = SupabaseVectorStore(
    client=supabase_client,
    table_name="books",
    embedding=embeddings,
    query_name="match_books"
    )

recipes_vector_store = SupabaseVectorStore(
    client=supabase_client,
    table_name="recipes_v2",
    embedding=embeddings,
    query_name="match_recipes_v2"
    )
# Define MemorySaver instance for langgraph agent
memory = MemorySaver()


# Create the agent tools for the RAG functions

####################################################################
# Similarity Search (Books)
####################################################################
def create_books_similarity_search_tool():
    @tool
    def get_books_similarity_search(input: str) -> str:
        """
        Tool to perform a simple similarity search on the 'books' vector store.
        Returns the top matching chunks as JSON.
        """
        query = input.strip()
        results = perform_books_similarity_search(query, books_vector_store)
        # 'perform_similarity_search' might return Documents or a custom structure.
        # Convert it to JSON or a string
        return json.dumps(results, default=str)
    return get_books_similarity_search


####################################################################
# Retrieval QA (Books)
####################################################################
def create_books_retrieval_qa_tool():
    @tool
    def get_books_retrieval_qa(input: str) -> str:
        """
        Tool for short Q&A over the 'books' corpus using retrieval QA.
        """
        query = input.strip()
        chain_result = perform_books_retrieval_qa(query, chat_llm, books_vector_store)
        # Typically returns a dict with 'answer', 'sources', 'source_documents', etc.
        return json.dumps(chain_result, default=str)
    return get_books_retrieval_qa

####################################################################
# Similarity Search (Recipes)
####################################################################
def create_recipes_similarity_search_tool():
    @tool
    def get_recipes_similarity_search(input: str) -> str:
        """
        Tool to perform a simple similarity search on the 'recipes' vector store.
        Returns the top matching chunks as JSON.
        """
        query = input.strip()
        results = perform_recipes_similarity_search (query, chat_llm, recipes_vector_store)
        return json.dumps(results, default=str)
    return get_recipes_similarity_search


####################################################################
# Self-Query Retrieval (Recipes)
####################################################################
def create_recipes_self_query_tool():
    @tool
    def get_recipes_self_query(input: str) -> str:
        """
        Tool for searching recipes with metadata-based self-query retrieval.
        (E.g., filter by recipe_type, cuisine, special_considerations, etc.)
        """
        query = input.strip()
        results = perform_recipes_self_query_retrieval(query, chat_llm, recipes_vector_store, SupabaseVectorTranslator())
        return json.dumps(results, default=str)
    return get_recipes_self_query

####################################################################
# Multi-Query Tool (Recipes)
####################################################################
def create_recipes_multi_query_tool():
    @tool
    def get_recipes_multi_query(input: str) -> str:
        """
        Tool for searching recipes with metadata-based self-query and multi-query retrieval .
        (E.g., filter by recipe_type, cuisine, special_considerations, etc.)
        """
        query = input.strip()
        results = perform_recipes_multi_query_retrieval(query, chat_llm, recipes_vector_store, SupabaseVectorTranslator())
        return json.dumps(results, default=str)
    return get_recipes_multi_query


# Routes
# Index route
@app.route("/", methods=["GET"])
# @login_required - Temporarily disabled for testing
def index():
    return render_template("index.html")  # Serve the chat interface

# Stream route with database tools
@app.route("/stream", methods=["GET"])
# @login_required - Temporarily disabled for testing
def stream():
    log.info(f"Stream request received with query: {request.args.get('query', '')}")
    
    # Get the query from the request
    query = request.args.get("query", "")
    if not query:
        log.error("Empty query received")
        return Response("data: Error: Empty query\n\n", content_type="text/event-stream")
    
    log.info(f"Processing query: {query}")
    
    # Create the database tools
    try:
        recipes_similarity_search_tool = create_recipes_similarity_search_tool()
        recipes_self_query_tool = create_recipes_self_query_tool()
        recipes_multi_query_tool = create_recipes_multi_query_tool()
        books_retrieval_qa_tool = create_books_retrieval_qa_tool()
        books_similarity_search_tool = create_books_similarity_search_tool()
        log.info("All tools created successfully")
    except Exception as e:
        log.error(f"Error creating tools: {str(e)}")
        return Response(f"data: Error creating tools: {str(e)}\n\n", content_type="text/event-stream")
    
    # System message with instructions to format recipes in a card-friendly way
    system_message_content = """You are ChefBoost, a helpful cooking assistant that provides recipe information and cooking advice from a database. 
    
When providing recipes, format them in this exact structured way:

1. Start with "Title: [Recipe Name]" on the first line
2. Then add "Recipe Type: [Type]" where type is one of: dessert, appetizer, main course, soup, salad, beverage, breakfast, side dish
3. Then add "Cuisine: [Cuisine]" where cuisine is the origin (e.g., Italian, French, Thai, etc.)
4. Then add "Special Considerations: [Any dietary notes]" for allergies or diets (e.g., vegetarian, gluten-free, dairy-free)
5. Then "Ingredients:" followed by a bulleted list (use - for bullets)
6. Add "Instructions:" followed by numbered steps (use 1. 2. 3. etc.)
7. ALWAYS add "Source: [Source]" with either the source of the recipe or "ChefBoost AI" if created by you
8. ALWAYS add "Date: [Date]" with the current date

Important: 
- DO NOT use markdown formatting like bold (** **), just use plain text
- ALWAYS use the exact headings shown above with colons (:)
- When multiple recipes are requested, create separate recipes with Title: at the start of each
- Keep each recipe complete with ALL fields
- When answering non-recipe questions, provide clear, helpful responses as a cooking assistant
- You have access to tools to search a database of recipes and cooking information

Example format:
Title: Italian Tiramisu
Recipe Type: dessert
Cuisine: Italian  
Special Considerations: contains eggs and dairy
Ingredients:
- 6 egg yolks
- 3/4 cup sugar
- 16 oz mascarpone cheese
- 1 1/2 cups strong brewed coffee, cooled
- 24 ladyfinger cookies
- 1/4 cup cocoa powder for dusting
Instructions:
1. Beat egg yolks and sugar until light and fluffy
2. Fold in mascarpone cheese until smooth
3. Quickly dip each ladyfinger in coffee and arrange in serving dish
4. Spread half the mascarpone mixture over ladyfingers
5. Add another layer of dipped ladyfingers
6. Top with remaining mascarpone mixture
7. Dust with cocoa powder and refrigerate for at least 4 hours
Source: Traditional Italian Cookbook
Date: 04/06/2025"""
    
    # Create the agent with tools
    try:
        graph = create_react_agent(
            model=chat_llm,
            tools=[   
                recipes_similarity_search_tool,
                recipes_self_query_tool,
                recipes_multi_query_tool,
                books_retrieval_qa_tool,
                books_similarity_search_tool,
            ],
            checkpointer=memory,
            prompt=system_message_content,
            debug=True
        )
        log.info("Agent graph created successfully")
    except Exception as e:
        log.error(f"Error creating agent: {str(e)}")
        return Response(f"data: Error creating LLM agent: {str(e)}\n\n", content_type="text/event-stream")

    # Setup inputs for the agent
    user_message = HumanMessage(content=query)
    inputs = {"messages": [user_message]}
    config = {"configurable": {"thread_id": "thread-1"}}
    
    HEARTBEAT_INTERVAL = 5

    @stream_with_context
    def generate():
        try:
            log.info("Starting agent stream generation")
            
            # Send spinner marker immediately, properly quoted with JSON
            yield f"data: {json.dumps('[spinner]')}\n\n"
            log.info("Initial spinner marker sent")
            
            # Initialize stream iterator from the agent graph
            stream_iterator = graph.stream(inputs, config, stream_mode="messages")
            
            last_sent_time = time.time()
            current_output = ""
            
            # Process messages from the stream
            while True:
                # Check if we've been idle too long
                if time.time() - last_sent_time > HEARTBEAT_INTERVAL:
                    # Send a heartbeat that won't interfere with display
                    yield f"data: {json.dumps('[keepalive]')}\n\n"
                    log.info("Keepalive sent")
                    last_sent_time = time.time()
                
                try:
                    # Get next message and metadata
                    msg, metadata = next(stream_iterator)
                except StopIteration:
                    # No more data from the agent
                    log.info("Stream iteration complete")
                    break
                except Exception as e:
                    # On any exception in stream iterator, report it and stop
                    log.error(f"Error during stream iteration: {str(e)}")
                    yield f"data: {json.dumps(f'Error: {str(e)}')}\n\n"
                    yield f"data: {json.dumps('[DONE]')}\n\n"
                    return
                
                # Update timestamp to prevent heartbeats during active streaming
                last_sent_time = time.time()
                
                # Skip user messages
                if hasattr(msg, 'type') and msg.type == 'human':
                    log.info("Skipping user message")
                    continue
                
                # Process message content if available
                if hasattr(msg, 'content') and msg.content:
                    # Skip echoes of the user's query
                    if msg.content.lower() == query.lower():
                        log.info("Skipping echo of user query")
                        continue
                        
                    log.info(f"Message content: {msg.content[:100]}...")
                    current_output += msg.content
                
                # Break on finish signal
                if metadata.get("finish_reason") == "stop":
                    log.info("Received final message with stop reason")
                    break
            
            # Send the accumulated response
            log.info(f"Sending full response with length {len(current_output)}")
            yield f"data: {json.dumps(current_output)}\n\n"
            
            # Final marker
            log.info("Sending DONE marker")
            yield f"data: {json.dumps('[DONE]')}\n\n"
        
        except GeneratorExit:
            # Client disconnected, log it but don't return anything
            log.info("Client disconnected, generator exited.")
            return
        
        except Exception as e:
            # Catch any other exceptions
            log.error(f"Unexpected error in stream: {str(e)}")
            yield f"data: {json.dumps(f'Error in stream: {str(e)}')}\n\n"
            yield f"data: {json.dumps('[DONE]')}\n\n"

    return Response(
        generate(),
        content_type="text/event-stream"
    )

# Sign up route
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()
        if user:
            flash("Username already registered.", "error")
            return redirect(url_for("signup"))

        new_user = User(
            username=username,
            email=email,
            password=generate_password_hash(password, method="pbkdf2:sha256")
        )
        db.session.add(new_user)
        db.session.commit()
        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")

# Login route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password, password):
            flash("Invalid username or password.", "error")
            return redirect(url_for("login"))

        login_user(user)
        flash("Logged in successfully!", "success")
        return redirect("/")

    return render_template("login.html")

# My Account route
@app.route("/my_account", methods=["GET", "POST"])
@login_required
def my_account():
    if request.method == "POST":
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if not check_password_hash(current_user.password, current_password):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("my_account"))

        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return redirect(url_for("my_account"))

        current_user.password = generate_password_hash(new_password, method="pbkdf2:sha256")
        db.session.commit()
        flash("Password updated successfully!", "success")
        return redirect(url_for("index"))

    return render_template("my_account.html", user=current_user)

# Logout route
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

# Function to add to the log
def log_run(run_status):
    if run_status in ["cancelled", "failed", "expired"]:
        log.error(str(datetime.datetime.now()) + " Run " + run_status)

# Add CORS headers to all responses
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'  # Allow all origins
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

# Run the Flask server
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Ensure the database is created
    app.run(debug=True, threaded=True)