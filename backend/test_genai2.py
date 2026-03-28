from google import genai
from config import settings
client = genai.Client(api_key=settings.GEMINI_API_KEY)
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Tell me a joke.'
)
print(response.text)
