import requests
from fastapi import FastAPI
from pydantic import BaseModel
from pymongo import MongoClient
from analysis import router as trip_router
import json
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("API_KEY")
mongo_uri = os.getenv("MONGO_URI")

app = FastAPI()

app.include_router(trip_router)

mongo_client = MongoClient(mongo_uri)
db = mongo_client["CarPulse"]
collection_summary = db["DriverSummary"]
collection_all = db["AverageDriverData"]
collection_trips = db["TripSummary"]

PPLX_API_KEY = api_key
PPLX_API_URL = "https://api.perplexity.ai/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {PPLX_API_KEY}",
    "Content-Type": "application/json"
}


class QuestionRequest(BaseModel):
    question: str | None = None
    user_id: str
    trip_id: str | None = None
    user: bool  | None = None

def extract_after_think(text: str) -> str:
    text = text.replace("*", "")
    return text.split("</think>")[-1].strip()

def call_perplexity(prompt: str, model="r1-1776"):
    data = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a concise assistant  for driving. Answer clearly and directly and no more than 5 sentences. Dont use * char in respones."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "stream": False
    }

    response = requests.post(PPLX_API_URL, headers=HEADERS, json=data)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


@app.post("/ask")
def ask_question(data: QuestionRequest):
    question = data.question
    user_id = data.user_id
    trip_id = data.trip_id
    user = data.user

    if trip_id:
        trip = collection_trips.find_one({"Trip ID": trip_id})
        if not trip:
            return {"error": f"Trip with ID {trip_id} not found."}

        context = json.dumps(trip, indent=2, default=str)
        question = "Analyze this trip in detail, longer than 5 sentences if needed. Answer like you are taking to the driver"
        prompt = f"Trip data:\n{context}\n\nQuestion: {question}"
        answer = call_perplexity(prompt)
        answer = extract_after_think(answer)

        return {"response": answer}

    if user:
        user_data = collection_summary.find_one({"Email": user_id})
        if not user_data:
            return {"error": f"User  with ID {user_id} not found."}

        context = json.dumps(user_data, indent=2, default=str)
        question = "Analyze this driver average data in detail, longer than 5 sentences if needed. Answer like you are taking to the driver "
        prompt = f"Driver data:\n{context}\n\nQuestion: {question}"
        answer = call_perplexity(prompt)
        answer = extract_after_think(answer)

        return {"response": answer}


    intent_prompt = f"""
Classify the user's question into one of:
- get_user_average
- compare_user_to_all
- get_current_trip
- no_data_needed

Only return the label. No reasoning, no explanation. 
Question: {question}
""".strip()

    raw_intent = call_perplexity(intent_prompt)
    intent = extract_after_think(raw_intent)

    if intent == "get_user_average":
        user_data = collection_summary.find_one({"Email": user_id})
        context = json.dumps(user_data, indent=2, default=str)
        prompt = f"User's average driving data:\n{context}\n\nQuestion: {question}"

    elif intent == "compare_user_to_all":
        user_data = collection_summary.find_one({"Email": user_id})
        all_data = collection_all.find_one({})
        context = json.dumps({"user": user_data, "all": all_data}, indent=2, default=str)
        prompt = f"User and global driving data:\n{context}\n\nQuestion: {question}"

    else:
        prompt = f"Question: {question}"

    raw_answer = call_perplexity(prompt)
    answer = extract_after_think(raw_answer)

    return {
        "response": answer,
        "intent": intent
    }

