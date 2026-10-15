# the modules of the simulator import each other by name: pytest from any folder finds them here
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
