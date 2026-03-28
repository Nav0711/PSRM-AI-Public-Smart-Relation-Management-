import sys
try:
    import google.generativeai as old_genai
    print("Old SDK installed:", old_genai.__version__)
except BaseException as e:
    print("Old SDK Error:", e)

try:
    from google import genai
    print("New SDK installed, Client available?", hasattr(genai, "Client"))
except BaseException as e:
    print("New SDK Error:", e)
