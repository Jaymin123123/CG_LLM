import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

client = OpenAI(api_key=OPENAI_API_KEY)

EXTRACTOR_MODEL = "gpt-5"      # for reading long Rem section
JUDGE_MODEL = "gpt-5"      # for cheap, many-judgments loop
EXTRACT_MODEL = "gpt-4.1"