import datetime
from fastapi import Body, FastAPI, Request
import ollama
import chromadb
import uuid
import requests
import os
from dotenv import load_dotenv
from langsmith import Client
import spacy
from spacy.matcher import Matcher

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

nlp = spacy.load("en_core_web_trf")
matcher = Matcher(nlp.vocab)

def detect_action(text):
    """Detects if the user is trying to create, update, or delete an object."""
    action_patterns = {
        "create": [["create"], ["add"], ["make"], ["new"]],
        "delete": [["delete"], ["remove"], ["erase"]],
        "update": [["update"], ["change"], ["modify"]],
        "list": [["list"], ["show"], ["view"]],
    }

    doc = nlp(text.lower())
    for action, patterns in action_patterns.items():
        for pattern in patterns:
            if all(token.text in [t.text for t in doc] for token in nlp(" ".join(pattern))):
                return action
    return "unknown"

def detect_object(text):
    """Detects if the user is referring to a board, list, or card."""
    object_patterns = {
        "board": [["board"]],
        "list": [["list"]],
        "card": [["card"]],
    }

    doc = nlp(text.lower())
    for obj, patterns in object_patterns.items():
        for pattern in patterns:
            if all(token.text in [t.text for t in doc] for token in nlp(" ".join(pattern))):
                return obj
    return "unknown"
import re

def extract_entities(text):
    """Extracts key details (action type, object type, name, lists) from user input using spaCy."""
    doc = nlp(text)
    extracted_info = {
        "action_type": None,
        "object_type": None,
        "name": None,
        "description": None,
        "lists": [],
        "other_parameters": {}
    }

    # Detect Named Entities (NER)
    for ent in doc.ents:
        if ent.label_ in ["ORG", "PRODUCT"]:  # Trello objects often classified under ORG/PRODUCT
            extracted_info["name"] = ent.text
        elif ent.label_ == "DATE":
            extracted_info["other_parameters"]["due_date"] = ent.text
        elif ent.label_ == "PERSON":
            extracted_info["other_parameters"]["member"] = ent.text

    #Rule-based intent detection
    extracted_info["action_type"] = detect_action(text)
    extracted_info["object_type"] = detect_object(text)

    #Extract lists from user input (if present)
    list_match = re.search(r"lists?:\s*(.*)", text, re.IGNORECASE)  # Find lists section
    if list_match:
        list_text = list_match.group(1)
        extracted_info["lists"] = [name.strip() for name in re.split(r",|\band\b", list_text)]  # Split by commas or "and"

    return extracted_info

@app.post("/prompt")
async def ask(request: Request):
    """Process a user request and generate the proper action using LLM for information extraction"""
    
    body = await request.json()
    action = body.get("action", "").strip()
    
    if not action:
        return {"error": "No action provided in the request."}

    # Extract structured information using spaCy
    extracted_info = extract_entities(action)

    # If spaCy fails, use LLM for extraction
    if not extracted_info["action_type"] or extracted_info["object_type"] == "unknown":
        extraction_prompt = ChatPromptTemplate.from_messages([
            # ("system", """You are an AI assistant specialized in extracting structured information from user requests related to Trello.
            # Extract the following details:
            # - Action type: create, list, update, delete, etc.
            # - Object type: board, list, card, etc.
            # - Name: The name provided for the object
            # - Description: Any description provided
            # - Other parameters: Due dates, labels, members, etc.
            # - Lists: ["id":"name"], etc.
            
            # Based on the user request, analyze the intent and generate a structured plan.
            # If a user wants to create a board, decide if lists and cards should be added.
            # Decide the name and content of each board, list and card based on the name of the object,
            # and the user intent.

            # Respond ONLY with a JSON object containing these fields. If a field is missing, set its value to null.
            # """),
            # ("user", "{request}")
            ("system", """You are an AI assistant specialized in extracting structured information from user requests related to Trello.
            Extract the following details:
            - Action type: create, list, update, delete, etc.
            - Object type: board, list, card, etc.
            - Name: The name provided for the object.
            - Description: Any description provided.
            - Other parameters: Due dates, labels, members, etc.
            - Lists: A list of names for lists to create. If the user specifies them, extract exactly what they said.
            - Example user input: 'Create a board for Work with lists: Urgent, Pending, Completed'
            - Extracted lists should be: ["Urgent", "Pending", "Completed"]

            Ensure lists are **ALWAYS extracted** if the user provides them.
            """)

        ])
        
        # Format prompt & convert to Ollama format
        extraction_messages = extraction_prompt.format_messages(request=action)
        ollama_extraction_messages = convert_messages_to_ollama(extraction_messages)

        try:
            extraction_response = ollama.chat(
                model="llama3.2",
                messages=ollama_extraction_messages
            )
            extracted_info.update(json.loads(extraction_response["message"]["content"]))
        except:
            pass  #If LLM fails, continue with spaCy-extracted data

    #Get past conversations for context
    try:
        results = collection.query(query_texts=[action], n_results=5)
        past_conversations = results["documents"][0] if results["documents"] else ["No relevant past conversations found."]
    except Exception as e:
        past_conversations = [f"Error retrieving past conversations: {str(e)}"]

    #Determine action type and object type
    action_type = extracted_info.get("action_type")
    object_type = extracted_info.get("object_type")

    #Create a Trello Board
    if action_type == "create" and object_type == "board":
        board_name = extracted_info.get("name") or "Default"
        description = extracted_info.get("description")        
        
        print("Extracted Info:", extracted_info)  # Debugging
        list_names = extracted_info.get("lists", [])
        print("Extracted Lists:", list_names)  # Debugging
        
        url = "https://api.trello.com/1/boards/"
        board_params = {
            "name": board_name,
            "desc": description,
            # "defaultLists": 0,
            "key": TRELLO_API_KEY,
            "token": TRELLO_TOKEN,
        }
        
        try:
            #Create the Board
            board_response = requests.post(url, params=board_params)
            if board_response.status_code != 200:
                return {"error": f"Failed to create Trello board. {board_response.text}"}

            board_data = board_response.json()
            board_id = board_data["id"]

            #Create Lists in the Board (if specified)
            created_lists = []
            for list_name in list_names:
                list_url = "https://api.trello.com/1/lists"
                list_params = {
                    "name": list_name,
                    "idBoard": board_id,
                    "key": TRELLO_API_KEY,
                    "token": TRELLO_TOKEN
                }
                list_response = requests.post(list_url, params=list_params)
                if list_response.status_code == 200:
                    created_list = list_response.json()
                    print(f"Created list: {created_list}")  # Debugging
                    created_lists.append(created_list)
                else:
                    print(f"Error creating list {list_name}: {list_response.text}")  # Debugging

            #Return success message
            answer = f"I've created a new Trello board called '{board_name}'"
            if description:
                answer += f" with description: '{description}'."
            if created_lists:
                list_names_str = ', '.join([lst['name'] for lst in created_lists])
                answer += f" It includes the lists: {list_names_str}."

            store_conversation(action, answer)
            return {"answer": answer, "board": board_data, "lists": created_lists}

        except Exception as e:
            return {"error": f"Error creating Trello board and lists: {str(e)}"}
    #Delete a Trello Board
    elif action_type == "delete" and object_type == "board":
        board_name = extracted_info.get("name")
        if not board_name:
            return {"error": "No board name provided. Please specify the board you want to delete."}

        url_get_boards = "https://api.trello.com/1/members/me/boards"
        params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}

        try:
            boards_response = requests.get(url_get_boards, params=params)
            if boards_response.status_code != 200:
                return {"error": f"Failed to retrieve Trello boards. {boards_response.text}"}

            boards = boards_response.json()
            board_id = next((b["id"] for b in boards if b["name"].lower() == board_name.lower()), None)
            if not board_id:
                return {"error": f"Board '{board_name}' not found in your Trello account."}

            # Delete the board
            url_delete = f"https://api.trello.com/1/boards/{board_id}"
            delete_response = requests.delete(url_delete, params=params)
            if delete_response.status_code == 200:
                answer = f"I've deleted the board called '{board_name}' from your account."
                store_conversation(action, answer)
                return {"answer": answer, "deleted_board_name": board_name, "extracted_info": extracted_info}
            else:
                return {"error": f"Failed to delete Trello board. {delete_response.text}"}
        except Exception as e:
            return {"error": f"Error deleting Trello board: {str(e)}"}

    #Handle Unsupported Actions Gracefully
    try:
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

        response_messages = response_prompt.format_messages(
            request=action,
            past_conversations=past_conversations
        )
        ollama_response_messages = convert_messages_to_ollama(response_messages)

        response = ollama.chat(
            model="llama3.2",
            messages=ollama_response_messages
        )
        answer = response["message"]["content"]
        store_conversation(action, answer)

        return {"answer": answer, "extracted_info": extracted_info}

    except Exception as e:
        return {"error": f"Error handling unsupported action: {str(e)}", "extracted_info": extracted_info}


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