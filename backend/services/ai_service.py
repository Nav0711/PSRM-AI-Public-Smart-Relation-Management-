from google import genai
from config import settings
import json
from celery_app import celery_app
from sqlalchemy.orm import Session
from utils.database import SessionLocal
from models.complaint import Complaint
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the client with API key
client = genai.Client(api_key=settings.GEMINI_API_KEY)
MODEL_ID = 'gemini-2.5-flash'

def classify_complaint_text(text: str, channel: str, ward: str = None):
    prompt = f"""
    Analyze the following citizen complaint and extract the details in strict JSON format.
    Complaint: {text}
    Channel: {channel}
    Ward: {ward}
    
    Return ONLY a JSON object with this schema:
    {{
      "category": "string (Water Supply, Roads & Infrastructure, Electricity, Healthcare, Education, Law & Order, Employment, Land Records, Sanitation, Other)",
      "subcategory": "string",
      "priority": "integer (1-5, 5 is most urgent)",
      "priority_reason": "string",
      "summary": "string (1-2 sentences)",
      "suggested_assignee_role": "string (FieldWorker / PA / Coordinator / Politician)",
      "suggested_action": "string",
      "draft_reply_citizen": "string (max 160 chars)",
      "language_detected": "string",
      "tags": ["array", "of", "tags"]
    }}
    """
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        text_resp = response.text.strip()
        if text_resp.startswith("```json"):
            text_resp = text_resp[7:-3]
        return json.loads(text_resp)
    except Exception as e:
        print(f"Error parsing Gemini response: {e}")
        return {"category": "Unclassified", "priority": 3, "summary": "Failed to classify"}

@celery_app.task
def classify_complaint_task(complaint_id: str, text: str, channel: str):
    """
    Background task to classify complaint using AI and update the database.
    This saves API calls by only running once per complaint creation.
    """
    try:
        # Generate AI classification
        logger.info(f"Starting AI classification for complaint {complaint_id}")
        result = classify_complaint_text(text, channel)
        
        # Update Database
        db = SessionLocal()
        try:
            complaint = db.query(Complaint).filter(Complaint.ticket_id == complaint_id).first()
            # If not found by ticket_id, try by UUID if that was passed (the caller passes ticket_id or id? Let's check router)
            # The router generates ticket_id but saves it. The id is UUID.
            # Let's check what I pass in the router. I will pass complaint.id (UUID) cast to str.
            
            if not complaint:
                complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
                
            if complaint:
                complaint.category = result.get("category", "Unclassified")
                complaint.subcategory = result.get("subcategory")
                complaint.priority = result.get("priority", 3)
                complaint.priority_reason = result.get("priority_reason")
                complaint.summary = result.get("summary")
                complaint.ai_overview = result.get("summary") 
                complaint.suggested_action = result.get("suggested_action")
                complaint.suggested_assignee_role = result.get("suggested_assignee_role")
                # complaint.assigned_to ... logic for assignment based on result['suggested_assignee_role'] can be added here
                # For now just storing the suggestion
                
                complaint.ai_draft_reply = result.get("draft_reply_citizen")
                complaint.language = result.get("language_detected", "Hindi")
                complaint.tags = result.get("tags", [])
                
                db.commit()
                logger.info(f"Successfully classified and updated complaint {complaint_id}")
            else:
                logger.error(f"Complaint {complaint_id} not found in database")
        except Exception as db_e:
            logger.error(f"Database error in classify_complaint_task: {db_e}")
            db.rollback()
        finally:
            db.close()
            
        return {"status": "success", "complaint_id": complaint_id, "classification": result}
    except Exception as e:
        logger.error(f"Error in classify_complaint_task: {e}")
        return {"status": "error", "error": str(e)}

def generate_morning_briefing(stats: dict):
    prompt = f"Generate a morning briefing summary and trend alert based on these stats: {json.dumps(stats)}. Return JSON with 'ai_summary' and 'trend_alert'."
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        text_resp = response.text.strip()
        if text_resp.startswith("```json"):
            text_resp = text_resp[7:-3]
        return json.loads(text_resp)
    except:
        return {"ai_summary": "Briefing generation failed.", "trend_alert": "No alerts."}

def identify_assignment_intent(message: str, context_data: str):
    prompt = f"""
    Analyze the user's message and the provided database context to identify which complaint (Ticket ID) they want to assign and to which worker.
    
    Database Context (Recent Complaints & Workers):
    {context_data}
    
    User Message: "{message}"
    
    Return ONLY a JSON object:
    {{
      "ticket_id": "CMP-XXXXX (the identified ticket id or null)",
      "worker_name": "Name of the identified worker or null",
      "description": "A short, 1-2 sentence instruction or task note derived from the user's message, directed at the worker (or null)",
      "found": boolean (true if you confidently matched BOTH a ticket and a worker based on the context, else false)
    }}
    """
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        text_resp = response.text.strip()
        if "```json" in text_resp:
            text_resp = text_resp.split("```json")[-1].split("```")[0]
        return json.loads(text_resp)
    except:
        return {"found": False}

def chat_with_data(message: str, history: list, query_type: str, context_data: str = ""):
    history_str = ""
    for msg in history:
        role = getattr(msg, "role", "user") if not isinstance(msg, dict) else msg.get("role", "user")
        content = getattr(msg, "content", "") if not isinstance(msg, dict) else msg.get("content", "")
        history_str += f"{role.upper()}: {content}\n\n"
        
    prompt = f"""
You are PSRM-AI, a strictly guarded AI Co-Pilot for a politician or field worker managing a constituency.
You MUST follow these rules (GUARDRAILS):
1. You may ONLY answer questions related to the provided Database Context below, OR help the user with the system's features (such as generating speeches, briefings, or media responses based on the data).
2. If the user asks a general knowledge question, trivia, coding help, or anything unrelated to the database or the constituency management platform, you MUST politely refuse to answer. State that you are restricted to constituency database inquiries.
3. Be concise and professional. Do not use markdown asterisks.
4. IMPORTANT: Always provide multiple items (like lists of complaints, workers, or tasks) as a clear, bulleted or numbered list. Each item should be on a new line.

### Database Context:
{context_data}

### Chat History:
{history_str}

### Current User Message:
{message}

Please respond to the Current User Message following the Guardrails.
"""
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt
    )
    return response.text

