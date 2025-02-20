from fastapi import FastAPI
import ollama
import chromadb
import uuid
import requests
import os
from dotenv import load_dotenv

# Initialize FastAPI app
app = FastAPI()

load_dotenv()
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
# TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID")

# Initialize ChromaDB client (in-memory for now, use persist_directory for saving)
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="chat_history")



@app.get("/ask")
def ask(question: str):
    """Process a user question and provide an answer."""

# Retrieve relevant past conversations (if any exist)
    results = collection.query(query_texts=[question], n_results=50)

    # Extract previous responses (if they exist)
    past_conversations = []
    if results and "documents" in results:
        past_conversations = results["documents"]  
    else:
        past_conversations = ["No relevant past conversations found."]
        
    processed_question = f"""
    Before answering, review relevant past conversations:
    {past_conversations}

    If past conversations contain a similar question to "{question}", use them to improve your answer.

    Step-by-step reasoning:
    1. What is the user asking?
    2. What context do past conversations provide?
    3. Does the question need a different response based on past interactions?
    4. What is the most accurate and complete response?

    Respond with only the final answer, without explanations of your thought process.

    User question: {question}
    """
    # Default behavior: Ask Llama for an answer
    response = ollama.chat(
    model="llama3.2",
    # model="deepseek-r1:8b",
    messages=[{"role": "user", "content": processed_question}])
    
    answer = response["message"]["content"]
    # Store conversation in ChromaDB
    collection.add(
        ids=[str(uuid.uuid4())],  # Unique ID (can be timestamped for better retrieval)
        documents=[f"Q: {question}\nA: {answer}"],  # Store full interaction
        metadatas=[{"question": question, "answer": answer}]  # Store metadata for easy retrieval
    )

    return {"answer": answer}

@app.get("/getBoards")
def get_boards():
    """Fetch all boards associated with the authenticated Trello user."""

    url = f"https://api.trello.com/1/members/me/boards"
    params = {
        "lists": "all",
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        return {"boards": response.json()}
    else:
        return {"error": "Failed to fetch Trello boards", "status_code": response.status_code}

@app.get("/getLists")
def get_lists(board_id: str):
    """Fetch all lists for a given Trello board."""

    url = f"https://api.trello.com/1/boards/{board_id}/lists"
    params = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        return {"lists": response.json()}
    else:
        return {"error": "Failed to fetch Trello lists", "status_code": response.status_code}
