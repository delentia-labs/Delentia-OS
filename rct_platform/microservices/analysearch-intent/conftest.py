import sys
from pathlib import Path

# Add the microservice root to sys.path so 'app.*' imports work
sys.path.insert(0, str(Path(__file__).parent))
