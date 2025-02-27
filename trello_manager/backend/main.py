import datetime
from fastapi import Body, FastAPI, Request
import ollama
import chromadb
import uuid
import requests
import os
from dotenv import load_dotenv
from langsmith import Client

from langchain_core.prompts import ChatPromptTemplate
  # Parse the JSON response
import json
import re
        
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

@app.post("/prompt")
async def ask(request: Request):
    """Process a user request and generates the proper action using LLM for information extraction"""
    
    body = await request.json()  # Get full JSON body
    action = body.get("action", "").strip()  # Extract action

    if not action:
        return {"error": "No action provided in the request."}

    # First, use the LLM to analyze the request and extract structured information
    extraction_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an AI assistant specialized in extracting structured information from user requests related to Trello.
            
    For each request, extract the following details if present:
    - Action type: create, list, update, delete, etc.
    - Object type: board, list, card, etc.
    - Name: The name provided for the object
    - Description: Any description provided
    - Other parameters: Due dates, labels, members, etc.

    Respond ONLY with a JSON object containing these fields. If a field is not present in the request, set its value to null."""),
    ("user", "{request}")
    ])
    
    # Format the extraction prompt
    extraction_messages = extraction_prompt.format_messages(request=action)
    ollama_extraction_messages = convert_messages_to_ollama(extraction_messages)
    
    # Get structured information from the LLM
    try:
        extraction_response = ollama.chat(
            model="llama3.2",
            messages=ollama_extraction_messages
        )
        
        extracted_info_text = extraction_response["message"]["content"]
        
        try:
            extracted_info = json.loads(extracted_info_text)
        except json.JSONDecodeError:
            # Fallback to a simple structure if JSON parsing fails
            extracted_info = {
                "action_type": "create" if "create" in action.lower() else ("delete" if "delete" in action.lower() else "other"),
                "object_type": "board" if "board" in action.lower() else "unknown",
                "name": None,
                "description": None,
                "other_parameters": {}
            }
                
        # Regex patterns to match different ways of specifying a name
        name_patterns = [
            r"name\s*[:=]?\s*(\w[\w\s]*)",         # Matches "name: XYZ" or "name = XYZ"
            r"called\s+([\w\s]+)",                 # Matches "called XYZ"
            r"named\s+([\w\s]+)",                  # Matches "named XYZ"
            r"create\s+(?:a\s+new\s+)?board\s+(?:called|named)\s+([\w\s]+)"  # Matches "create a new board called XYZ"
        ]

        for pattern in name_patterns:
            match = re.search(pattern, action, re.IGNORECASE)
            if match:
                extracted_info["name"] = match.group(1).strip()
                break  # Stop at the first valid match

                
    except Exception as e:
        return {"error": f"Error extracting information from request: {str(e)}"}
    
    # Get past conversations for context
    try:
        results = collection.query(
            query_texts=[action],
            n_results=5
        )
        past_conversations = results["documents"][0] if results["documents"] else ["No relevant past conversations found."]
    except Exception as e:
        past_conversations = [f"Error retrieving past conversations: {str(e)}"]
    
    # Execute Trello actions based on extracted information
    action_type = extracted_info.get("action_type")
    object_type = extracted_info.get("object_type")
    
    # Create a board
    if action_type == "create" and object_type == "board":
        # Use the extracted name or a default
        board_name = extracted_info.get("name") or "New Trello Board by Jorge"
        
        # Check for description and other parameters
        description = extracted_info.get("description")
        other_params = extracted_info.get("other_parameters", {})
        
        # Prepare Trello API call parameters
        url = "https://api.trello.com/1/boards/"
        params = {
            "name": {board_name},
            "defaultLists": None,
            "defaultLists": None,
            "key": TRELLO_API_KEY,
            "token": TRELLO_TOKEN,
        }
        
        # Add description if present
        if description:
            params["desc"] = description
        
        # Add any other supported parameters
        if "background_color" in other_params:
            params["prefs_background"] = other_params["background_color"]
        
        if "visibility" in other_params:
            params["prefs_permissionLevel"] = other_params["visibility"]
        
        try:
            reply = requests.post(url, params=params)
            
            if reply.status_code == 200:
                board_data = reply.json()
                answer = f"I've created a new Trello board called '{board_name}'"
                if description:
                    answer += f" with description: '{description}'"
                answer += f". You can access it at {board_data.get('url', 'your Trello account')}."
                
                # Store conversation in ChromaDB
                store_conversation(action, answer)
                
                return {
                    "answer": answer, 
                    "board": board_data,
                    "extracted_info": extracted_info
                }
            else:
                answer = f"Failed to create Trello board. Status code: {reply.status_code}. Message: {reply.text}"
                return {"error": answer, "extracted_info": extracted_info}
                
        except Exception as e:
            answer = f"Error creating Trello board: {str(e)}"
            return {"error": answer, "extracted_info": extracted_info}
        
     # Delete a board
   # Delete a board
# Delete a board
    elif action_type == "delete" and object_type == "board":
        board_name = extracted_info.get("name")

    if not board_name:
        return {"error": "No board name provided. Please specify the board you want to delete."}

    # 1. Get the list of boards to find the board ID
    url_get_boards = f"https://api.trello.com/1/members/me/boards"
    params = {
        "name": {board_name},
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN
    }

    try:
        boards_response = requests.get(url_get_boards, params=params)

        if boards_response.status_code != 200:
            return {"error": f"Failed to retrieve Trello boards. {boards_response.text}"}

        boards = boards_response.json()
        board_id = next((board["id"] for board in boards if board["name"].lower() == board_name.lower()), None)

        if not board_id:
            return {"error": f"Board '{board_name}' not found in your Trello account."}

        # 2. Delete the board using the found ID
        url_delete = f"https://api.trello.com/1/boards/{board_id}"

        delete_response = requests.delete(url_delete, params=params)

        if delete_response.status_code == 200:
            answer = f"I've deleted the board called '{board_name}' from your account."

            # Store conversation in ChromaDB
            store_conversation(action, answer)

            return {
                "answer": answer,
                "deleted_board_name": board_name,
                "extracted_info": extracted_info
            }
        else:
            return {"error": f"Failed to delete Trello board. Status code: {delete_response.status_code}. Message: {delete_response.text}"}

    except Exception as e:
        return {"error": f"Error deleting Trello board: {str(e)}"}
    
    # For other types of requests or unsupported actions
    else:
        response_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant specialized in Trello task management."),
            ("user", f"""
            Request: {action}

            Past conversations for context: {past_conversations}

            Based on this request related to Trello, provide a helpful response.
            If the request appears to be asking for an action that's not implemented yet, 
            politely explain what capabilities are currently available.
            """)
                    ])
        
        # response_messages = response_prompt.format_messages()
        # The fix: Pass the required variables to format_messages()
        response_messages = response_prompt.format_messages(
            request=action,
            past_conversations=past_conversations
        )
        ollama_response_messages = convert_messages_to_ollama(response_messages)
        
        try:
            response = ollama.chat(
                model="llama3.2",
                messages=ollama_response_messages
            )
            answer = response["message"]["content"]
            
            # Store conversation in ChromaDB
            store_conversation(action, answer)
            
            return {"answer": answer, "extracted_info": extracted_info}
        except Exception as e:
            answer = f"Error generating response: {str(e)}"
            return {"error": answer, "extracted_info": extracted_info}

# Helper function to store conversations in ChromaDB
def store_conversation(request, answer):
    try:
        collection.add(
            ids=[str(uuid.uuid4())],
            documents=[f"Q: {request}\nA: {answer}"],
            metadatas=[{
                "request": request,
                "answer": answer,
                "timestamp": datetime.datetime.now().isoformat()
            }]
        )
    except Exception as e:
        print(f"Failed to store conversation: {str(e)}")


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
