import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    SERPER_API_KEY = os.getenv("SERPER_API_KEY")
    
    # If True, agents will use dummy data instead of real API calls
    # This allows the code to run without costing money or requiring keys immediately
    MOCK_MODE = os.getenv("MOCK_MODE", "True").lower() == "true"
    
    # Directory to save generated reports/charts
    UPLOAD_DIR = "uploads"
    os.makedirs(UPLOAD_DIR, exist_ok=True)