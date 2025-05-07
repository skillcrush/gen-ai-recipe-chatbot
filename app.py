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

from langchain.agents import tool
from langchain_community.query_constructors.supabase import SupabaseVectorTranslator
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain.prompts import PromptTemplate
from langchain.chains import HypotheticalDocumentEmbedder

# RAG imports
from gutenberg.books_storage_and_retrieval import (
    perform_similarity_search as perform_books_similarity_search,
    perform_retrieval_qa as perform_books_retrieval_qa,
    perform_rag_step_back_prompting as perform_books_rag_step_back_prompting,
    perform_rag_decomposition as perform_books_rag_decomposition,
    perform_rag_decomposition_answer_recursively as perform_books_rag_decomposition_answer_recursively,
    perform_rag_decomposition_answer_individually as perform_books_rag_decomposition_answer_individually
)

from gutenberg.recipes_storage_and_retrieval_v2 import (
    perform_similarity_search as perform_recipes_similarity_search,
    perform_self_query_retrieval as perform_recipes_self_query_retrieval,
    perform_multi_query_retrieval as perform_recipes_multi_query_retrieval,
    perform_rag_fusion_retrieval as perform_recipes_rag_fusion_retrieval,
    perform_self_query_rag_fusion_retrieval as perform_recipes_self_query_rag_fusion_retrieval
)

# Load environment variables from a .env file
load_dotenv(override=True)

# Set up logging in the app.log file
log = logging.getLogger("assistant")
logging.basicConfig(filename="app.log", level=logging.INFO)

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

# ====================== HYDE CHANGES: Define base embeddings & LLM ====================== #
base_embeddings = OpenAIEmbeddings(openai_api_key=api_key)

hyde_prompt_template = """Generate an recipe that matches the user's request: {REQUEST}
Recipe:"""
hyde_prompt = PromptTemplate(input_variables=["REQUEST"], template=hyde_prompt_template)

# Use HyDE embedder with the "web_search" prompt (or replace with your custom prompt)
embeddings = HypotheticalDocumentEmbedder.from_llm(
    llm=chat_llm,
    base_embeddings=base_embeddings,
    custom_prompt=hyde_prompt
)

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
# RAG Step-Back Prompting (Books)
####################################################################

def create_books_rag_step_back_prompting_tool():
    @tool
    def get_books_rag_step_back_prompting(input: str) -> str:
        """
        Tool for RAG Step-Back Prompting, generating a generic paraphrased question
        and retrieving both original & stepped-back context.
        """
        query = input.strip()
        results = perform_books_rag_step_back_prompting(query, chat_llm, books_vector_store)
        return json.dumps(results, default=str)
    return get_books_rag_step_back_prompting

####################################################################
# RAG Decomposition (Books)
####################################################################
def create_books_rag_decomposition_tool():
    @tool
    def get_books_rag_decomposition(input: str) -> str:
        """
        Tool for multi-step RAG Decomposition (standard) on the 'books' corpus.
        """
        query = input.strip()
        results = perform_books_rag_decomposition(query, chat_llm, books_vector_store)
        # Usually returns a dict with sub-queries, answers, sources
        return json.dumps(results, default=str)
    return get_books_rag_decomposition


####################################################################
# RAG Decomposition Answer Recursively (Books)
####################################################################
def create_books_rag_decomposition_recursive_tool():
    @tool
    def get_books_rag_decomposition_recursive(input: str) -> str:
        """
        Tool for RAG Decomposition with an iterative/recursive approach.
        """
        query = input.strip()
        results = perform_books_rag_decomposition_answer_recursively(query, chat_llm, books_vector_store)
        return json.dumps(results, default=str)
    return get_books_rag_decomposition_recursive


####################################################################
# RAG Decomposition Answer Individually (Books)
####################################################################
def create_books_rag_decomposition_individual_tool():
    @tool
    def get_books_rag_decomposition_individual(input: str) -> str:
        """
        Tool for RAG Decomposition that answers sub-questions individually,
        then synthesizes a final answer.
        """
        query = input.strip()
        results = perform_books_rag_decomposition_answer_individually(query, chat_llm, books_vector_store)
        return json.dumps(results, default=str)
    return get_books_rag_decomposition_individual


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
        Tool for searching recipes with metadata-based self-query and multi-query retrieval.
        (E.g., filter by recipe_type, cuisine, special_considerations, etc.)
        """
        query = input.strip()
        results = perform_recipes_multi_query_retrieval(query, chat_llm, recipes_vector_store, SupabaseVectorTranslator())
        return json.dumps(results, default=str)
    return get_recipes_multi_query

####################################################################
# RAG Fusion Retrieval (Recipes)
####################################################################
def create_recipes_rag_fusion_tool():
    @tool
    def get_recipes_rag_fusion(input: str) -> str:
        """
        Tool for multi-query + reciprocal rank fusion retrieval over the 'recipes' corpus.
        Useful for broad coverage of ambiguous or multi-faceted recipe requests.
        """
        query = input.strip()
        # Adjust 'num_queries' as needed
        results = perform_recipes_rag_fusion_retrieval(query, chat_llm, recipes_vector_store, num_queries=4)
        return json.dumps(results, default=str)
    return get_recipes_rag_fusion


####################################################################
# Self-Query + RAG Fusion Combined (Recipes)
####################################################################
def create_recipes_self_query_rag_fusion_tool():
    @tool
    def get_recipes_self_query_rag_fusion(input: str) -> str:
        """
        Tool for combining multi-angle (RAG Fusion) retrieval with
        metadata-based self-query filtering on the 'recipes' corpus.
        """
        query = input.strip()
        results = perform_recipes_self_query_rag_fusion_retrieval(
            query,
            multi_query_llm=chat_llm,   # or a different LLM if desired
            self_query_llm=chat_llm,
            vector_store=recipes_vector_store,
            structured_query_translator=SupabaseVectorTranslator(),
            num_queries=4
        )
        return json.dumps(results, default=str)
    return get_recipes_self_query_rag_fusion

# Routes
# Index route
@app.route("/", methods=["GET"])
@login_required
def index():
    return render_template("index.html")  # Serve the chat interface

# Stream route
@app.route("/stream", methods=["GET"])
@login_required
def stream():

    recipes_similarity_search_tool = create_recipes_similarity_search_tool()
    recipes_self_query_tool = create_recipes_self_query_tool()
    recipes_multi_query_tool = create_recipes_multi_query_tool()
    recipes_rag_fusion_tool = create_recipes_rag_fusion_tool()
    recipes_self_query_rag_fusion_tool = create_recipes_self_query_rag_fusion_tool()
    books_retrieval_qa_tool = create_books_retrieval_qa_tool()
    books_similarity_search_tool = create_books_similarity_search_tool()
    books_rag_step_back_prompting_tool = create_books_rag_step_back_prompting_tool()
    books_rag_decomposition_tool = create_books_rag_decomposition_tool()
    books_rag_decomposition_recursive_tool = create_books_rag_decomposition_recursive_tool()
    books_rag_decomposition_individual_tool = create_books_rag_decomposition_individual_tool()

    graph = create_react_agent(
        model=chat_llm,
        tools=[   
            recipes_similarity_search_tool,
            recipes_self_query_tool,
            recipes_multi_query_tool,
            recipes_rag_fusion_tool,
            recipes_self_query_rag_fusion_tool,
            books_retrieval_qa_tool,
            books_similarity_search_tool,
            books_rag_step_back_prompting_tool,
            books_rag_decomposition_tool,
            books_rag_decomposition_recursive_tool,
            books_rag_decomposition_individual_tool
        ],
        checkpointer=memory,
        debug=True
    )

    inputs = {"messages": [("user", request.args.get("query", ""))]}
    config = {"configurable": {"thread_id": "thread-1"}}

    @stream_with_context
    def generate():
        HEARTBEAT_INTERVAL = 5
        try:
            log.info("Starting agent stream generation")
            
            # Send spinner marker immediately, properly quoted with JSON
            yield f"data: {json.dumps('[spinner]')}\n\n"
            log.info("Initial spinner marker sent")
            
            stream_iterator = graph.stream(inputs, config, stream_mode="messages")
            current_node = None
            current_output = ""
            last_sent_time = time.time()
            
            while True:
                # Check if we've been idle too long, send heartbeat if needed
                if time.time() - last_sent_time > HEARTBEAT_INTERVAL:
                    yield f"data: {json.dumps('[keepalive]')}\n\n"
                    log.info("Keepalive sent")
                    last_sent_time = time.time()
                    
                try:
                    msg, metadata = next(stream_iterator)
                except StopIteration:
                    log.info("Stream iteration complete")
                    break
                except Exception as e:
                    log.error(f"Error during stream iteration: {str(e)}")
                    yield f"data: {json.dumps(f'Error: {str(e)}')}\n\n"
                    yield f"data: {json.dumps('[DONE]')}\n\n"
                    return
                
                # Update timestamp to prevent heartbeats during active streaming
                last_sent_time = time.time()

                node = metadata.get("langgraph_node")
                # If we detect a change in the node, assume previous output was intermediate.
                if current_node is None:
                    current_node = node
                    log.info(f"Initial node: {node}")
                elif node != current_node:
                    log.info(f"Node changed from {current_node} to {node}")
                    current_node = node
                    current_output = ""  # reset accumulator for new node

                if msg.content:
                    current_output += msg.content

                # Once we get a finish signal for the current node, we break out.
                if metadata.get("finish_reason") == "stop":
                    log.info("Received final message with stop reason")
                    break
        except GeneratorExit:
            log.info("Client disconnected, generator exited.")
            return  # client disconnected
        except Exception as e:
            log.error(f"Unexpected error in stream: {str(e)}")
            yield f"data: {json.dumps(f'Error: {str(e)}')}\n\n"
            yield f"data: {json.dumps('[DONE]')}\n\n"
            return

        # Yield only the final aggregated output from the last node
        log.info(f"Sending full response with length {len(current_output)}")
        yield f"data: {json.dumps(current_output)}\n\n"
        yield f"data: {json.dumps('[DONE]')}\n\n"

    return Response(generate(), content_type="text/event-stream")

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

# Function to add to the log in the app.log file
def log_run(run_status):
    if run_status in ["cancelled", "failed", "expired"]:
        log.error(str(datetime.datetime.now()) + " Run " + run_status + "\n")

# Run the Flask server
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Ensure the database is created
    app.run(debug=True)
