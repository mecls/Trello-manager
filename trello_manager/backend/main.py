import datetime
from fastapi import FastAPI, Query
import ollama
import chromadb
import uuid
import requests
import os
from dotenv import load_dotenv
from langsmith import Client
from langchain_core.prompts import ChatPromptTemplate

# Initialize FastAPI app
app = FastAPI()

# Load environment variables
load_dotenv()
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
LANGSMITH_API_KEY = os.getenv("LANGCHAIN_API_KEY")

# Initialize ChromaDB client
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="chat_history")

# Connect to the LangSmith client
client = Client()

def convert_messages_to_ollama(messages):
    """Convert LangChain formatted messages to Ollama format."""
    converted_messages = []
    for message in messages:
        if hasattr(message, 'type') and hasattr(message, 'content'):
            role = 'system' if message.type == 'system' else 'user'
            converted_messages.append({
                "role": role,
                "content": message.content
            })
    return converted_messages

@app.get("/prompt")
async def ask(action: str = Query(..., title="User Question", description="Enter a question for the chatbot")):
    """Process a user question and provide an AI-generated response."""
    
    # Define the prompt template
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful chatbot specialized in task management and organization."),
        ("user", "{question}")
    ])

    # Get past conversations
    try:
        results = collection.query(
            query_texts=[action],
            n_results=50
        )
        past_conversations = results["documents"][0] if results["documents"] else ["No relevant past conversations found."]
    except Exception as e:
        past_conversations = [f"Error retrieving past conversations: {str(e)}"]

    # Process the question with context
    processed_question = f"""
    Past conversations for context: {past_conversations}

    Current question: {action}

    Please provide a direct and relevant response based on both the current question and any applicable past context.
    """

    # Format the prompt
    formatted_messages = prompt.format_messages(question=processed_question)
    
    # Convert messages to Ollama format
    ollama_messages = convert_messages_to_ollama(formatted_messages)

    # Generate response using Ollama
    try:
        response = ollama.chat(
            model="llama3.2",
            messages=ollama_messages
        )
        answer = response["message"]["content"]
    except Exception as e:
        return {"error": f"Error generating response: {str(e)}"}

    # Store conversation in ChromaDB
    try:
        collection.add(
            ids=[str(uuid.uuid4())],
            documents=[f"Q: {action}\nA: {answer}"],
            metadatas=[{
                "question": action,
                "answer": answer,
                "timestamp": datetime.datetime.now().isoformat()
            }]
        )
    except Exception as e:
        return {"error": f"Failed to store conversation: {str(e)}", "answer": answer}

    return {"answer": answer}

@app.get("/getBoards")
def get_boards():
    """Fetch all boards associated with the authenticated Trello user."""

    url = f"https://api.trello.com/1/members/me/boards"
    params = {
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
    
@app.get("/getCards")
def get_cards(list_id: str):
    """Fetch all cards for a given Trello list."""

    url = f"https://api.trello.com/1/lists/{list_id}/cards"
    params = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN   
    }
    
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return {"cards": response.json()}
    else:   
        return {"error": "Failed to fetch Trello cards", "status_code": response.status_code}
    
@app.get("/getFields")
def get_fields(id: str, field:str):
    """Fetch all fields for a given Trello list."""

    url = f"https://api.trello.com/1/cards/{id}/{field}"

    params = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN
    }
    
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return {"fields": response.json()}
    else:   
        return {"error": "Failed to fetch Trello fields", "status_code": response.status_code}
